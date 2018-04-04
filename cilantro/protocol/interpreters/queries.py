import hashlib
import time
from sqlalchemy import *
from cilantro.db.delegate import tables


def contract(tx):
    def pending(ctx):
        def execute(*args, **kwargs):
            ctx('use scratch;')
            r = ctx(*args, **kwargs)

            if r is not None:
                return r

            ctx('use state')
            r = ctx(*args, **kwargs)

            return r

        return execute

    def format_query(*args, **kwargs):
        globals()['tables'].db.execute = pending(globals()['tables'].db.execute)
        deltas = tx(*args, **kwargs)

        if deltas is None:
            return None

        try:
            deltas[0]
        except TypeError:
            deltas = [deltas]

        new_deltas = []
        for delta in deltas:
            new_deltas.append(str(delta.compile(compile_kwargs={'literal_binds': True})))

        return new_deltas

    return format_query

class StandardQuery:
    """
    StandardQuery
    Automates the state and txq modifications for standard transactions
    """

    @contract
    def process_tx(self, tx):

        q = select([tables.balances.c.amount]).where(tables.balances.c.wallet == tx.sender)

        sender_balance = tables.db.execute(q).fetchone()

        if sender_balance is None:
            return None

        if sender_balance[0] >= tx.amount:

            q = select([tables.balances.c.amount]).where(tables.balances.c.wallet == tx.receiver)

            recv_row = tables.db.execute(q).fetchone()

            if recv_row is None:
                receiver_q = insert(tables.balances).values(
                    wallet=tx.receiver,
                    amount=tx.amount
                )

            else:
                receiver_q = update(tables.balances).values(
                    wallet=tx.receiver,
                    amount=recv_row[0] + tx.amount
                )

            sender_q = update(tables.balances).values(
                wallet=tx.sender,
                amount=sender_balance[0] - tx.amount
            )

            return sender_q, receiver_q
        else:
            return None


class VoteQuery:
    """
    VoteQuery
    Automates the state modifications for vote transactions
    """

    @contract
    def process_tx(self, tx):
        q = insert(tables.votes).values(
            wallet=tx.sender,
            policy=tx.policy,
            choice=tx.choice
        )
        return q


class SwapQuery:
    """
    SwapQuery
    Automates the state modifications for swap transactions
    Rules:
    Sender cannot overwrite this value / update it, so fail if the swap cannot insert (on interpreter side?)
    """

    @contract
    def process_tx(self, tx):
        q = select([tables.balances.c.amount]).where(tables.balances.c.wallet == tx.sender)

        row = tables.db.execute(q).fetchone()

        sender_balance = 0 if row is None else row[0]

        if sender_balance >= tx.amount:

            new_sender_balance = sender_balance - tx.amount

            balance_q = update(tables.balances).values(
                wallet=tx.sender,
                amount=new_sender_balance
            )

            swap_q = insert(tables.swaps).values(
                sender=tx.sender,
                receiver=tx.receiver,
                amount=tx.amount,
                expiration=tx.expiration,
                hashlock=tx.hashlock
            )

            return balance_q, swap_q

        else:
            return None


class RedeemQuery:
    @contract
    def process_tx(self, tx):
        # calculate the hashlock from the secret. if it is incorrect, the query will fail
        hashlock = hashlib.sha3_256()
        hashlock.update(bytes.fromhex(tx.secret))
        hashlock = hashlock.digest().hex()

        # build the query assuming that this is a redeem, not a refund
        q = select([tables.swaps.c.amount, tables.swaps.c.expiration]).where(and_(
            tables.swaps.c.receiver == tx.sender,
            tables.swaps.c.hashlock == hashlock
        ))

        # get the data from the db. let's assume that people reuse secrets (BAD!), and so we will iterate through
        # all of the queries we got back.

        deltas = []

        for amount, expiration in tables.db.execute(q).cursor:
            print(amount, expiration)

            if int(expiration) > int(time.time()):
                # awesome
                q = select([tables.balances.c.amount]).where(tables.balances.c.wallet == tx.sender)

                balance = tables.db.execute(q).fetchone()

                balance = 0 if balance is None else balance[0]

                new_balance = balance + amount

                q = update(tables.balances).values(
                    wallet=tx.sender,
                    amount=new_balance
                )

                deltas.append(q)

                q = delete(tables.swaps).where(
                    and_(
                        tables.swaps.c.receiver == tx.sender,
                        tables.swaps.c.hashlock == hashlock,
                        tables.swaps.c.amount == amount,
                        tables.swaps.c.expiration == expiration,
                    )
                )

                deltas.append(q)

        # check the opposing side. IE, if the sender is the original swap creator and wants a refund

        q = select([tables.swaps.c.amount, tables.swaps.c.expiration, tables.swaps.c.receiver]).where(and_(
            tables.swaps.c.sender == tx.sender,
            tables.swaps.c.hashlock == hashlock
        ))

        for amount, expiration, receiver in tables.db.execute(q).cursor:
            if int(expiration) < time.time():
                q = select([tables.balances.c.amount]).where(tables.balances.c.wallet == tx.sender)

                balance = tables.db.execute(q).fetchone() or 0

                new_balance = balance[0] + amount

                q = insert(tables.balances).values(
                    wallet=tx.sender,
                    amount=new_balance
                )

                deltas.append(q)

                q = delete(tables.swaps).where(
                    and_(
                        tables.swaps.c.sender == tx.sender,
                        tables.swaps.c.receiver == receiver,
                        tables.swaps.c.hashlock == hashlock,
                        tables.swaps.c.amount == amount,
                        tables.swaps.c.expiration == expiration,
                    )
                )
                deltas.append(q)

        if len(deltas) > 0:
            return deltas

        return None
