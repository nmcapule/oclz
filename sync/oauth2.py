from sync import constants

class Oauth2Service:
    """Implements tracking of Oauth2 tokens."""

    def __init__(self, dbpath=None):
        self._db_client = self._Connect(dbpath or constants._DEFAULT_DB_PATH)

        self._Setup()

    def __enter__(self):
        return self

    def __exit__(self, unused_exc_type, unused_exc_value, unused_traceback):
        self.Close()

    def _Setup(self):
        """Creates all table in the database."""
        cursor = self._db_client.cursor()
        cursor.execute(constants._CREATE_TABLE_OAUTH2)
        self._db_client.commit()

    def _Drop(self):
        """Drops all table in the database."""
        cursor = self._db_client.cursor()
        cursor.execute(constants._DROP_TABLE_OAUTH2)
        self._db_client.commit()

    def _Connect(self, dbpath):
        """Creates a connection to sqlite3 database."""
        return sqlite3.connect(dbpath)

    def _Disconnect(self):
        """Dsiconnects from sqlite3 datbase."""
        self._db_client.close()
        self._db_client = None

    def Close(self):
        """Safely closes connection to sqlite3 database."""
        if self._db_client:
            self._Disconnect()

    def SaveOauth2Tokens(self, system, access_token, refresh_token, expires_on):
        """Saves the oauth2 tokens of a system to the database."""
        cursor = self._db_client.cursor()

        cursor.execute(
            """
            UPDATE oauth2
            SET access_token=?, refresh_token=?, expires_on=?, created_on=CURRENT_TIMESTAMP
            WHERE system=?
            """,
            (access_token, refresh_token, expires_on, system),
        )

        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO oauth2 (system, access_token, refresh_token, expires_on)
                VALUES (?, ?, ?, ?)
                """,
                (system, access_token, refresh_token, expires_on),
            )

        self._db_client.commit()

    def GetOauth2Tokens(self, system):
        """Retrieves latest tokens from a system.

        Returns:
            dict, detail of Oauth2 tokens for a system.
        """

        cursor = self._db_client.cursor()

        cursor.execute(
            """
            SELECT system, access_token, refresh_token, created_on, expires_on
            FROM oauth2
            WHERE system=?
            """,
            (system,),
        )

        result = cursor.fetchone()
        if result is None:
            raise NotFoundError("Oauth2 for system not found: %s" % system)

        return {
            "system": result[0],
            "access_token": result[1],
            "refresh_token": result[2],
            "created_on": result[3],
            "expires_on": result[4],
        }
