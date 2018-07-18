from cilantro import Constants
from cilantro.utils.test import MPTesterBase, MPTestCase, mp_testable, MPComposer, vmnet_test
from cilantro.protocol.transport import Router, Composer
from cilantro.protocol.reactor import ReactorInterface
from cilantro.messages import *
from cilantro.protocol.wallets import ED25519Wallet
from cilantro.protocol.reactor.executor import *
from cilantro.db import VKBook
import asyncio
import unittest
import time


W = Constants.Protocol.Wallets
# sk1, vk1 = W.new()
# sk2, vk2 = W.new()
# sk3, vk3 = W.new()
# sk4, vk4 = W.new()
sk1, vk1 = Constants.Testnet.Masternodes[0]['sk'], Constants.Testnet.Masternodes[0]['vk']
sk2, vk2 = Constants.Testnet.Delegates[0]['sk'], Constants.Testnet.Delegates[0]['vk']
sk3, vk3 = Constants.Testnet.Delegates[1]['sk'], Constants.Testnet.Delegates[1]['vk']
sk4, vk4 = Constants.Testnet.Delegates[2]['sk'], Constants.Testnet.Delegates[2]['vk']

URL = 'tcp://127.0.0.1:9988'
FILTER = 'TEST_FILTER'

FILTERS = ['FILTER_' + str(i) for i in range(100)]
URLS = ['tcp://127.0.0.1:' + str(i) for i in range(9000, 9999, 10)]


def random_msg():
    return StandardTransactionBuilder.random_tx()

def random_envelope(sk=None, tx=None):
    sk = sk or ED25519Wallet.new()[0]
    tx = tx or random_msg()
    return Envelope.create_from_message(message=tx, signing_key=sk)


class TestSecureTransportIntegration(MPTestCase):

    @vmnet_test
    def test_pubsub_1_1_1(self):
        """
        Tests pub/sub 1-1 (one sub one pub) with one message
        """
        def config_sub(composer: Composer):
            from unittest.mock import MagicMock

            composer.interface.router = MagicMock()
            return composer

        def assert_sub(composer: Composer):
            from cilantro.messages import ReactorCommand, Envelope
            from cilantro.protocol.statemachine.decorators import StateInput
            cb = ReactorCommand.create_callback(callback=StateInput.INPUT, envelope=env)
            composer.interface.router.route_callback.assert_called_once_with(cb)

        env = random_envelope()

        sub = MPComposer(config_fn=config_sub, assert_fn=assert_sub, name='** [MN1] SUB', sk=sk1)
        pub = MPComposer(name='++ [Delegate1] PUB', sk=sk2)
        pub_ip = pub.ip

        sub.add_sub(vk=vk2, filter=FILTER)
        pub.add_pub(ip=pub_ip)

        time.sleep(0.2)

        pub.send_pub_env(filter=FILTER, envelope=env)

        self.start()

    # @vmnet_test
    # def test_pubsub_1_1_2_mult_filters(self):
    #     """
    #     Tests pub/sub 1-1 (one sub one pub) with 2 message each on a different filter
    #     """
    #     def configure(composer: Composer):
    #         from unittest.mock import MagicMock
    #         composer.interface.router = MagicMock()
    #         return composer
    #
    #     def run_assertions(composer: Composer):
    #         from cilantro.messages import ReactorCommand
    #         from cilantro.protocol.statemachine.decorators import StateInput
    #         from unittest.mock import call
    #
    #         cb1 = ReactorCommand.create_callback(callback=StateInput.INPUT, envelope=env1)
    #         cb2 = ReactorCommand.create_callback(callback=StateInput.INPUT, envelope=env2)
    #         composer.interface.router.route_callback.assert_has_calls([call(cb1), call(cb2)], any_order=True)
    #
    #     env1 = random_envelope()
    #     env2 = random_envelope()
    #     filter1 = FILTERS[0]
    #     filter2 = FILTERS[1]
    #
    #     sub = MPComposer(config_fn=configure, assert_fn=run_assertions, name='** SUB', sk=sk1)
    #     pub = MPComposer(name='++ PUB', sk=sk2)
    #
    #     sub.add_sub(vk=vk2, filter=filter2)
    #     sub.add_sub(vk=vk2, filter=filter1)
    #     pub.add_pub(ip=pub.ip)
    #
    #     time.sleep(3.0)  # allow time for VK lookups before we start sending things
    #
    #     # Send 2 envelopes on 2 different filters
    #     pub.send_pub_env(filter=filter1, envelope=env1)
    #     pub.send_pub_env(filter=filter2, envelope=env2)
    #
    #     self.start()

    # @vmnet_test
    # def test_req_reply_1_1_1(self):
    #     """
    #     Tests request/reply 1_1_1
    #     """
    #     def config_router(composer: Composer):
    #         from unittest.mock import MagicMock
    #         def reply(*args, **kwargs):  # do i need the *args **kwargs ??
    #             composer.send_reply(message=reply_msg, request_envelope=request_env)
    #
    #         composer.interface.router = MagicMock()
    #         composer.interface.router.route_callback.side_effect = reply
    #         return composer
    #
    #     def config_dealer(composer: Composer):
    #         from unittest.mock import MagicMock
    #         composer.interface.router = MagicMock()
    #         return composer
    #
    #     def assert_dealer(composer: Composer):
    #         from cilantro.messages import ReactorCommand
    #
    #         args = composer.interface.router.route_callback.call_args_list
    #         assert len(args) == 1, "dealer's route_callback should of only been called once (with the reply env)"
    #
    #         call = args[0]
    #         callback_cmd = call[0][0]
    #
    #         assert isinstance(callback_cmd, ReactorCommand), "arg of route_callback should be a ReactorCommand"
    #         assert callback_cmd.envelope.message == reply_msg, "Callback's envelope's message should be the reply_msg"
    #
    #     def assert_router(composer: Composer):
    #         from cilantro.protocol.statemachine.decorators import StateInput
    #         from cilantro.messages import ReactorCommand
    #         cb = ReactorCommand.create_callback(callback=StateInput.REQUEST, envelope=request_env, header=dealer_id)
    #         composer.interface.router.route_callback.assert_called_once_with(cb)
    #
    #     dealer_id = vk1
    #     dealer_sk = sk1
    #     router_sk = sk2
    #     router_vk = vk2
    #
    #     request_env = random_envelope(sk=dealer_sk)
    #     reply_msg = random_msg()
    #
    #     dealer = MPComposer(name='DEALER', sk=sk1, config_fn=config_dealer, assert_fn=assert_dealer)
    #     router = MPComposer(config_fn=config_router, assert_fn=assert_router, name='ROUTER', sk=router_sk)
    #
    #     dealer.add_dealer(vk=router_vk)
    #     router.add_router(vk=router_vk)
    #
    #     time.sleep(1.0)
    #
    #     dealer.send_request_env(vk=router_vk, envelope=request_env)
    #
    #     self.start()

    # def test_req_reply_1_1_1_timeout(self):
    #     """
    #     Tests request/reply 1_1_1 with a timeout and a late reply
    #     """
    #     def config_router(composer: Composer):
    #         def reply(*args, **kwargs):  # do i need the *args **kwargs ??
    #             time.sleep(timeout_duration * 1.5)
    #             composer.send_reply(message=reply_msg, request_envelope=request_env)
    #
    #         composer.interface.router = MagicMock()
    #         composer.interface.router.route_callback.side_effect = reply
    #         return composer
    #
    #     def config_dealer(composer: Composer):
    #         composer.interface.router = MagicMock()
    #         return composer
    #
    #     def assert_dealer(composer: Composer):
    #         cb = ReactorCommand.create_callback(callback=StateInput.TIMEOUT, envelope=request_env)
    #         composer.interface.router.route_callback.assert_any_call(cb)
    #
    #     def assert_router(composer: Composer):
    #         cb = ReactorCommand.create_callback(callback=StateInput.REQUEST, envelope=request_env, header=dealer_id)
    #         composer.interface.router.route_callback.assert_called_once_with(cb)
    #
    #     timeout_duration = 0.5
    #
    #     dealer_id = vk1
    #     dealer_sk = sk1
    #     router_sk = sk2
    #     router_url = URLS[1]
    #
    #     request_env = random_envelope(sk=dealer_sk)
    #     reply_msg = random_msg()
    #
    #     dealer = MPComposer(name='DEALER', sk=sk1, config_fn=config_dealer, assert_fn=assert_dealer)
    #     router = MPComposer(config_fn=config_router, assert_fn=assert_router, name='ROUTER', sk=router_sk)
    #
    #     dealer.add_dealer(url=router_url)
    #     router.add_router(url=router_url)
    #
    #     time.sleep(0.2)
    #
    #     dealer.send_request_env(url=router_url, envelope=request_env, timeout=timeout_duration)
    #
    #     self.start()


if __name__ == '__main__':
    unittest.main()
