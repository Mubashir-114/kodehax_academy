"""Initialize the pure-Python MySQL adapter before Django loads its backend."""
import pymysql
from pymysql.constants import CLIENT


class VerifiedTLSConnection(pymysql.connections.Connection):
    def _request_authentication(self):
        # PyMySQL otherwise falls back to plaintext if the server lacks TLS.
        # Refuse before sending authentication when TLS was requested.
        if self.ssl and not self.server_capabilities & CLIENT.SSL:
            raise pymysql.OperationalError("MySQL server does not support required TLS")
        return super()._request_authentication()


pymysql.connect = VerifiedTLSConnection
pymysql.install_as_MySQLdb()
