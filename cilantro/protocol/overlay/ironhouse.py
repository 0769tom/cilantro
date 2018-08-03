#!/usr/bin/env python

"""
Generate client and server CURVE certificate files then move them into the
appropriate store directory, private_keys or public_keys. The certificates
generated by this script are used by the stonehouse and ironhouse examples.
In practice this would be done by hand or some out-of-band process.
Author: Chris Laws
"""

import os, shutil, datetime
import asyncio, zmq
import zmq.auth, zmq.asyncio
from os.path import basename, splitext
from zmq.auth.thread import ThreadAuthenticator
from zmq.auth.asyncio import AsyncioAuthenticator
from zmq.utils.z85 import decode, encode
from nacl.public import PrivateKey, PublicKey
from nacl.signing import SigningKey, VerifyKey
from nacl.bindings import crypto_sign_ed25519_sk_to_curve25519
from cilantro.storage.db import VKBook
from cilantro.constants.overlay_network import AUTH_TIMEOUT
from cilantro.logger import get_logger

log = get_logger(__name__)

class Ironhouse:
    def __init__(self, sk=None, auth_validate=None, wipe_certs=False, auth_port=None, keyname=None, *args, **kwargs):
        self.auth_port = auth_port or os.getenv('AUTH_PORT', 4523)
        self.keyname = keyname or os.getenv('HOSTNAME', 'ironhouse')
        self.base_dir = 'certs/{}'.format(self.keyname)
        self.keys_dir = os.path.join(self.base_dir, 'certificates')
        self.public_keys_dir = os.path.join(self.base_dir, 'public_keys')
        self.secret_keys_dir = os.path.join(self.base_dir, 'private_keys')
        self.secret_file = os.path.join(self.secret_keys_dir, "{}.key_secret".format(self.keyname))
        if auth_validate:
            self.auth_validate = auth_validate
        else:
            self.auth_validate = Ironhouse.auth_validate
        self.wipe_certs = wipe_certs
        if sk:
            self.generate_certificates(sk)
        self.public_key, self.secret = zmq.auth.load_certificate(self.secret_file)

    def vk2pk(self, vk):
        return encode(VerifyKey(bytes.fromhex(vk)).to_curve25519_public_key()._public_key)

    def generate_certificates(self, sk_hex):
        sk = SigningKey(seed=bytes.fromhex(sk_hex))
        self.vk = sk.verify_key.encode().hex()
        self.public_key = self.vk2pk(self.vk)
        private_key = crypto_sign_ed25519_sk_to_curve25519(sk._signing_key).hex()

        for d in [self.keys_dir, self.public_keys_dir, self.secret_keys_dir]:
            if self.wipe_certs and os.path.exists(d):
                shutil.rmtree(d)
            os.makedirs(d, exist_ok=True)

        if self.wipe_certs:
            self.create_from_private_key(private_key)

            # move public keys to appropriate directory
            for key_file in os.listdir(self.keys_dir):
                if key_file.endswith(".key"):
                    shutil.move(os.path.join(self.keys_dir, key_file),
                                os.path.join(self.public_keys_dir, '.'))

            # move secret keys to appropriate directory
            for key_file in os.listdir(self.keys_dir):
                if key_file.endswith(".key_secret"):
                    shutil.move(os.path.join(self.keys_dir, key_file),
                                os.path.join(self.secret_keys_dir, '.'))

            log.info('Generated CURVE certificate files!')

    def create_from_private_key(self, private_key):
        priv = PrivateKey(bytes.fromhex(private_key))
        publ = priv.public_key
        self.public_key = public_key = encode(publ._public_key)
        secret_key = encode(priv._private_key)

        base_filename = os.path.join(self.keys_dir, self.keyname)
        secret_key_file = "{0}.key_secret".format(base_filename)
        public_key_file = "{0}.key".format(base_filename)
        now = datetime.datetime.now()

        zmq.auth.certs._write_key_file(public_key_file,
                        zmq.auth.certs._cert_public_banner.format(now),
                        public_key)

        zmq.auth.certs._write_key_file(secret_key_file,
                        zmq.auth.certs._cert_secret_banner.format(now),
                        public_key,
                        secret_key=secret_key)

    def create_from_public_key(self, public_key):
        if self.public_key == public_key:
            return
        keyname = decode(public_key).hex()
        base_filename = os.path.join(self.public_keys_dir, keyname)
        public_key_file = "{0}.key".format(base_filename)
        now = datetime.datetime.now()

        if os.path.exists(public_key_file):
            log.debug('Public cert for {} has already been created.'.format(public_key))
            return

        os.makedirs(self.public_keys_dir, exist_ok=True)
        log.info('Adding new public key cert {} to the system.'.format(public_key))

        zmq.auth.certs._write_key_file(public_key_file,
                        zmq.auth.certs._cert_public_banner.format(now),
                        public_key)

        self.reconfigure_curve()


    def secure_context(self, async=False):
        if async:
            ctx = zmq.asyncio.Context()
            auth = AsyncioAuthenticator(ctx)
            auth.log = log # The constructor doesn't have "log" like its synchronous counter-part
        else:
            ctx = zmq.Context()
            auth = ThreadAuthenticator(ctx, log=log)
        auth.start()
        self.reconfigure_curve(auth)

        return ctx, auth

    def reconfigure_curve(self, auth=None):
        if not auth:
            if not hasattr(self, 'auth'): return
            self.auth.configure_curve(domain='*', location=zmq.auth.CURVE_ALLOW_ANY)
        else:
            auth.configure_curve(domain='*', location=self.public_keys_dir)

    def secure_socket(self, sock, curve_serverkey=None):
        sock.curve_secretkey = self.secret
        sock.curve_publickey = self.public_key
        if curve_serverkey:
            # self.create_from_public_key(curve_serverkey) #NOTE Do not automatically trust
            sock.curve_serverkey = curve_serverkey
        else: sock.curve_server = True
        return sock

    async def authenticate(self, target_public_key, ip, port=None):
        if target_public_key == self.public_key: return 'authorized'
        try:
            PublicKey(decode(target_public_key))
        except Exception as e:
            log.debug('Invalid public key')
            return 'invalid'
        server_url = 'tcp://{}:{}'.format(ip, port or self.auth_port)
        log.debug('authenticating with {}...'.format(server_url))
        client = self.ctx.socket(zmq.REQ)
        client.setsockopt(zmq.LINGER, 0)
        client = self.secure_socket(client, target_public_key)
        client.connect(server_url)
        client.send(self.vk.encode())
        authorized = 'unauthorized'

        try:
            msg = await asyncio.wait_for(client.recv(), AUTH_TIMEOUT)
            msg = msg.decode()
            log.debug('got secure reply {}, {}'.format(msg, target_public_key))
            received_public_key = self.vk2pk(msg)
            if self.auth_validate(msg) == True and target_public_key == received_public_key:
                self.create_from_public_key(received_public_key)
                authorized = 'authorized'
        except Exception as e:
            log.debug('no reply from {} after waiting...'.format(server_url))
            authorized = 'no_reply'

        client.disconnect(server_url)
        client.close()
        self.auth.stop()

        return authorized

    def setup_secure_server(self):
        self.ctx, self.auth = self.secure_context(async=True)
        self.reconfigure_curve()
        self.sec_sock = self.secure_socket(self.ctx.socket(zmq.REP))
        self.sec_sock.bind('tcp://*:{}'.format(self.auth_port))
        self.server = asyncio.ensure_future(self.secure_server())

    def cleanup(self):
        if not self.auth._AsyncioAuthenticator__task.done():
            self.auth.stop()
        self.server.cancel()
        self.sec_sock.close()
        log.info('Ironhouse cleaned up properly.')

    async def secure_server(self):
        log.info('Listening to secure connections at {}'.format(self.auth_port))
        try:
            while True:
                message = await self.sec_sock.recv()
                message = message.decode()

                log.debug('got secure request {}'.format(message))

                if self.auth_validate(message) == True:
                    public_key = self.vk2pk(message)
                    self.create_from_public_key(public_key)
                    log.debug('sending secure reply: {}'.format(self.vk))
                    self.sec_sock.send(self.vk.encode())
        finally:
            self.cleanup()

    @staticmethod
    def auth_validate(vk):
        return vk in VKBook.get_all()
