"""Vrais serveurs SFTP et FTP locaux pour les tests (dans des threads).

SFTP : petit serveur bâti avec paramiko, qui sert un dossier du disque en lecture.
FTP : pyftpdlib.
"""

import os
import socket
import threading

import paramiko

USER, PASSWORD = "fournisseur", "secret-de-test"


class _Auth(paramiko.ServerInterface):
    def __init__(self, authorized_key=None):
        self.authorized_key = authorized_key

    def get_allowed_auths(self, username):
        return "password,publickey"

    def check_auth_publickey(self, username, key):
        ok = username == USER and self.authorized_key is not None and key == self.authorized_key
        return paramiko.AUTH_SUCCESSFUL if ok else paramiko.AUTH_FAILED

    def check_auth_password(self, username, password):
        ok = (username, password) == (USER, PASSWORD)
        return paramiko.AUTH_SUCCESSFUL if ok else paramiko.AUTH_FAILED

    def check_channel_request(self, kind, chanid):
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED


class _Handle(paramiko.SFTPHandle):
    def stat(self):
        return paramiko.SFTPAttributes.from_stat(os.fstat(self.readfile.fileno()))


def make_sftp_interface(root: str):
    class _Sftp(paramiko.SFTPServerInterface):
        def _path(self, path):
            return os.path.join(root, self.canonicalize(path).lstrip("/"))

        def list_folder(self, path):
            real = self._path(path)
            try:
                result = []
                for name in os.listdir(real):
                    attr = paramiko.SFTPAttributes.from_stat(os.stat(os.path.join(real, name)))
                    attr.filename = name
                    result.append(attr)
                return result
            except OSError as exc:
                return paramiko.SFTPServer.convert_errno(exc.errno)

        def stat(self, path):
            try:
                return paramiko.SFTPAttributes.from_stat(os.stat(self._path(path)))
            except OSError as exc:
                return paramiko.SFTPServer.convert_errno(exc.errno)

        lstat = stat

        def open(self, path, flags, attr):
            try:
                handle = _Handle(flags)
                handle.readfile = open(self._path(path), "rb")  # noqa: SIM115
                handle.filename = self._path(path)
                return handle
            except OSError as exc:
                return paramiko.SFTPServer.convert_errno(exc.errno)

    return _Sftp


class SftpServer:
    def __init__(self, root: str, authorized_key=None):
        self.authorized_key = authorized_key
        self.host_key = paramiko.ECDSAKey.generate()
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.interface = make_sftp_interface(root)
        self.transports: list[paramiko.Transport] = []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            transport = paramiko.Transport(conn)
            transport.add_server_key(self.host_key)
            transport.set_subsystem_handler("sftp", paramiko.SFTPServer, self.interface)
            transport.start_server(server=_Auth(self.authorized_key))
            self.transports.append(transport)

    def close(self):
        self.sock.close()
        for t in self.transports:
            t.close()


class FtpServer:
    def __init__(self, root: str):
        from pyftpdlib.authorizers import DummyAuthorizer
        from pyftpdlib.handlers import FTPHandler
        from pyftpdlib.servers import FTPServer

        authorizer = DummyAuthorizer()
        authorizer.add_user(USER, PASSWORD, root, perm="elr")  # lecture seule
        handler = type("Handler", (FTPHandler,), {"authorizer": authorizer})
        self.server = FTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.address[1]
        threading.Thread(
            target=self.server.serve_forever, kwargs={"handle_exit": False}, daemon=True
        ).start()

    def close(self):
        self.server.close_all()
