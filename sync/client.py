import sqlite3
import logging

from sync import constants
from sync.common import errors


class InventoryItem:
    """Describes an inventory item."""

    def __init__(self, model, stocks=0, last_sync_batch_id=0):
        self.model = model
        self.stocks = stocks
        self.last_sync_batch_id = last_sync_batch_id


class InventorySystemCacheItem(InventoryItem):
    """Describes an inventory item for an external system."""

    def __init__(self, model, system, stocks=0, last_sync_batch_id=0, not_behaving=0):
        self.model = model
        self.system = system
        self.stocks = stocks
        self.last_sync_batch_id = last_sync_batch_id
        self.not_behaving = not_behaving


class SyncClient:
    """Implements syncing."""

    def __init__(
        self,
        dbpath,
        opencart_client=None,
        lazada_client=None,
        shopee_client=None,
        woocommerce_client=None,
        default_client=None,
    ):
        self._opencart_client = opencart_client
        self._lazada_client = lazada_client
        self._shopee_client = shopee_client
        self._woocommerce_client = woocommerce_client
        self._default_client = default_client

        self._external_systems = []
        if self._opencart_client:
            self._external_systems.append(constants._SYSTEM_OPENCART)
            logging.info(f"Enabling system: {constants._SYSTEM_OPENCART}")
        if self._lazada_client:
            self._external_systems.append(constants._SYSTEM_LAZADA)
            logging.info(f"Enabling system: {constants._SYSTEM_LAZADA}")
        if self._shopee_client:
            self._external_systems.append(constants._SYSTEM_SHOPEE)
            logging.info(f"Enabling system: {constants._SYSTEM_SHOPEE}")
        if self._woocommerce_client:
            self._external_systems.append(constants._SYSTEM_WOOCOMMERCE)
            logging.info(f"Enabling system: {constants._SYSTEM_WOOCOMMERCE}")

        self._db_client = self._Connect(dbpath or constants._DEFAULT_DB_PATH)
        self.sync_batch_id = -1

        self._Setup()

    def __enter__(self):
        return self

    def __exit__(self, unused_exc_type, unused_exc_value, unused_traceback):
        self.Close()

    def _Connect(self, dbpath):
        """Creates a connection to sqlite3 database."""
        return sqlite3.connect(dbpath)

    def _Disconnect(self):
        """Dsiconnects from sqlite3 datbase."""
        self._db_client.close()
        self._db_client = None

    def _Setup(self):
        """Creates all table in the database."""
        cursor = self._db_client.cursor()
        cursor.execute(constants._CREATE_TABLE_SYNC_BATCH)
        cursor.execute(constants._CREATE_TABLE_SYNC_LOGS)
        cursor.execute(constants._CREATE_TABLE_INVENTORY_SYSTEM_CACHE)
        cursor.execute(constants._CREATE_TABLE_INVENTORY_SYSTEM_CACHE_DELTA)
        cursor.execute(constants._CREATE_TABLE_INVENTORY)

        self._db_client.commit()

    def _Drop(self):
        """Drops all table in the database."""
        cursor = self._db_client.cursor()
        cursor.execute(constants._DROP_TABLE_SYNC_BATCH)
        cursor.execute(constants._DROP_TABLE_SYNC_LOGS)
        cursor.execute(constants._DROP_TABLE_INVENTORY_SYSTEM_CACHE)
        cursor.execute(constants._DROP_TABLE_INVENTORY_SYSTEM_CACHE_DELTA)
        cursor.execute(constants._DROP_TABLE_INVENTORY)

        self._db_client.commit()

    def Close(self):
        """Safely closes connection to sqlite3 database."""
        if self._db_client:
            self._Disconnect()

    def PurgeAndSetup(self, system):
        """This reinitializes and defaults products from what is in Opencart.

        Args:
          system: str, The system code of which to use as a basis of new datasets.
        """
        self._Drop()
        self._Setup()
        self._PopulateInventoryFromSystem(system)

    def _InitSyncBatch(self):
        """Creates a new sync batch process record.

        Returns:
          int, The primary key of the sync batch.
        """
        cursor = self._db_client.cursor()

        cursor.execute(
            """INSERT INTO sync_batch (script_version) VALUES (?)""",
            (constants._SCRIPT_VERSION,),
        )

        self._db_client.commit()
        self.sync_batch_id = cursor.lastrowid

    def _System(self, system):
        """Returns the client for the given system.

        Args:
          system: str, The system code.

        Returns:
          LazadaClient or OpencartClient or ShopeeClient or WooCommerceClient, The client to use.

        Raises:
          UnhandledSystemError, The given system code not yet supported.
        """
        if system == constants._SYSTEM_LAZADA:
            return self._lazada_client
        elif system == constants._SYSTEM_OPENCART:
            return self._opencart_client
        elif system == constants._SYSTEM_SHOPEE:
            return self._shopee_client
        elif system == constants._SYSTEM_WOOCOMMERCE:
            return self._woocommerce_client
        else:
            raise UnhandledSystemError("System is not handled: %s" % system)

    def _PopulateInventoryFromSystem(self, system):
        """Repopulate inventory table with records from a given system.

        Args:
          system: str, The system code.

        Raises:
          UnhandledSystemError, The given system code not yet supported.
          CommunicationError: Cannot communicate with the system.
        """
        client = self._System(system)

        client.Refresh()
        for p in client.ListProducts():
            item = InventoryItem(
                model=p.model, stocks=p.stocks, last_sync_batch_id=self.sync_batch_id
            )
            self._UpsertInventoryItem(item)

    def _GetInventoryItem(self, model):
        """Retrieves a single InventoryItem.

        Args:
          model: string, The sku / model of the product being searched.

        Returns:
          InventoryItem, The product being searched.

        Raises:
          NotFoundError: The sku / model of the product is not in the database.
        """
        cursor = self._db_client.cursor()

        cursor.execute(
            """
            SELECT model, stocks, last_sync_batch_id
            FROM inventory
            WHERE model=?
            """,
            (model,),
        )

        result = cursor.fetchone()
        if result is None:
            raise errors.NotFoundError("InventoryItem not found: %s" % model)

        return InventoryItem(
            model=result[0], stocks=result[1], last_sync_batch_id=result[2]
        )

    def _GetInventoryItems(self):
        """Retrieves all items from the inventory.

        Returns:
            Array<InventoryItem>, List of inventory items
        """
        cursor = self._db_client.cursor()

        cursor.execute(
            """
            SELECT model, stocks, last_sync_batch_id
            FROM inventory
            """
        )

        result = []
        for p in cursor.fetchall():
            result.append(
                InventoryItem(model=p[0], stocks=p[1], last_sync_batch_id=p[2])
            )
        return result

    def _DeleteInventoryItems(self, models):
        """Deletes the given models from the inventory table."""
        cursor = self._db_client.cursor()
        for model in models:
            logging.info("Deleting item `%s` from inventory table" % model)
            cursor.execute(
                """
                DELETE FROM inventory
                WHERE model=?
                """,
                (model,),
            )

        self._db_client.commit()

    def _UpsertInventoryItem(self, item):
        """Updates a single InventoryItem record.

        Args:
          item: InventoryItem, The prodcut being updated.
        """
        cursor = self._db_client.cursor()

        cursor.execute(
            """
            UPDATE inventory
            SET stocks=?, last_sync_batch_id=?
            WHERE model=?
            """,
            (item.stocks, item.last_sync_batch_id, item.model),
        )

        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO inventory (model, stocks, last_sync_batch_id)
                VALUES (?, ?, ?)
                """,
                (item.model, item.stocks, item.last_sync_batch_id),
            )

        self._db_client.commit()

    def _GetInventorySystemCacheItem(self, system, model):
        """Retrieves a single InventorySystemCacheItem.

        Args:
          system: string, The system code.
          model: string, The sku / model of the product being searched.

        Returns:
          InventorySystemCacheItem, The product being searched.

        Raises:
          NotFoundError: The sku / model of the product is not in the cached system
              database.
        """
        cursor = self._db_client.cursor()

        cursor.execute(
            """
            SELECT model, system, stocks, last_sync_batch_id, not_behaving
            FROM inventory_system_cache
            WHERE model=? AND system=?
            """,
            (model, system),
        )

        result = cursor.fetchone()
        if result is None:
            raise errors.NotFoundError(
                "InventorySystemCacheItem not found: %s in %s" % (model, system)
            )

        return InventorySystemCacheItem(
            model=result[0],
            system=result[1],
            stocks=result[2],
            last_sync_batch_id=result[3],
            not_behaving=result[4],
        )
    
    def _MarkNotBehavingInventorySystemCacheItem(self, system, item, not_behaving):
        """Updates a single InventorySystemCacheItem's not_behaving flag."""
        cursor = self._db_client.cursor()

        logging.info(
            f"update: {item.model}({type(item.model)}) - {not_behaving}"
        )

        cursor.execute(
            """
            UPDATE inventory_system_cache
            SET not_behaving=?
            WHERE model=? AND system=?
            """,
            (not_behaving, item.model, system),
        )

        self._db_client.commit()

    def _UpsertInventorySystemCacheItem(self, system, item):
        """Updates a single InventorySystemCacheItem record.

        Args:
          item: InventoryItem, The prodcut being updated.
        """
        cursor = self._db_client.cursor()

        logging.info(
            f"upsert: {item.model}({type(item.model)}) - {item.stocks}({type(item.stocks)})"
            + f" {item.last_sync_batch_id}@{system}"
        )

        cursor.execute(
            """
            UPDATE inventory_system_cache
            SET stocks=?, last_sync_batch_id=?
            WHERE model=? AND system=?
            """,
            (item.stocks, item.last_sync_batch_id, item.model, system),
        )

        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO inventory_system_cache
                    (model, system, stocks, last_sync_batch_id)
                VALUES (?, ?, ?, ?)
                """,
                (item.model, system, item.stocks, item.last_sync_batch_id),
            )

        self._db_client.commit()

    def _CollectExternalProductModels(self, filter_system=None):
        """Returns a list of all unique product models from the external sources."""
        models = set([])

        for system in self._external_systems:
            if filter_system and system != filter_system:
                continue

            client = self._System(system)
            for p in client.ListProducts():
                # Skip falsy product models, ie: undefined, empty strings
                if not p.model:
                    continue
                models.add(p.model)

        return models

    def ProductAvailability(self):
        """Returns an object declaring product availability on each of the systems."""
        lookup = {}
        for system in self._external_systems:
            lookup[system] = set(self._CollectExternalProductModels(system))
        return lookup

    def _CalculateSystemStocksDelta(self, system, model):
        """Calculates the delta between last saw and current external system's
        stocks of a product."""
        client = self._System(system)

        try:
            current_stocks = client.GetProduct(model).stocks
            cached_item = self._GetInventorySystemCacheItem(system, model)
            if cached_item.not_behaving:
                cached_stocks = current_stocks
            else:
                cached_stocks = cached_item.stocks
        except Exception as e:
            logging.warn(e)
            return 0, 0

        return current_stocks - cached_stocks, current_stocks

    def _RecordSystemStocksDelta(self, system, model, stocks_delta, current_stocks):
        """Adds a record of the diff between cached and current stocks of an item
        in an external system."""
        cached_stocks = current_stocks - stocks_delta

        cursor = self._db_client.cursor()
        cursor.execute(
            """
            INSERT INTO inventory_system_cache_delta
                (model, system, cached_stocks, current_stocks, stocks_delta,
                 last_sync_batch_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                model,
                system,
                cached_stocks,
                current_stocks,
                stocks_delta,
                self.sync_batch_id,
            ),
        )

        self._db_client.commit()

    def _UpdateExternalSystemItem(self, system, item):
        """Update item attributes of an item in an external system.

        Args:
          system: str, The system code of the external system to be updated.
          item: InventoryItem, The item to be updated.

        Raises:
          NotFoundError: The sku / model of the product is not in the external
              system.
          MultipleResultsError: The sku / model is not unique in the external
              system.
          CommunicationError: Cannot communicate properly with the external system.
        """
        client = self._System(system)
        system_item = client.GetProduct(item.model)

        logging.info("Updating inventory system cache for %s %s" % (system, item.model))
        fresh_item = InventorySystemCacheItem(
            system=system,
            model=system_item.model,
            stocks=system_item.stocks,
            last_sync_batch_id=self.sync_batch_id,
        )
        self._UpsertInventorySystemCacheItem(system, fresh_item)

        if item.stocks == system_item.stocks:
            logging.info("No need to update %s in %s: same" % (item.model, system))
            return

        logging.info(f"Update {item.model}: {system_item.stocks} -> {item.stocks}")
        try:
            result = client.UpdateProductStocks(item.model, item.stocks)
            self._MarkNotBehavingInventorySystemCacheItem(system, item, False)
        except errors.PlatformNotBehavingError as e:
            self._MarkNotBehavingInventorySystemCacheItem(system, item, True)
            raise e

        # Create a record of syncing under sync_logs table.
        cursor = self._db_client.cursor()

        cursor.execute(
            """
            INSERT INTO sync_logs
              (sync_batch_id, system, model, previous_stocks, computed_stocks,
                  upload_error_code, upload_error_description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.sync_batch_id,
                system,
                item.model,
                system_item.stocks,
                item.stocks,
                int(result.error_code),
                str(result.error_description),
            ),
        )

        self._db_client.commit()

        # If successful in update, update in system cache.
        if result.error_code == constants._ERROR_SUCCESS:
            self._UpsertInventorySystemCacheItem(system, item)

    def Sync(self, read_only=False):
        """Executes the whole syncing batch process."""
        self._InitSyncBatch()

        for model in self._CollectExternalProductModels():
            stocks_delta = 0
            for system in self._external_systems:
                system_stocks_delta, current_stocks = self._CalculateSystemStocksDelta(
                    system, model
                )
                if system_stocks_delta != 0 and not read_only:
                    logging.info(
                        "Change in stocks of %s in %s: %d",
                        system,
                        model,
                        system_stocks_delta,
                    )
                    self._RecordSystemStocksDelta(
                        system, model, system_stocks_delta, current_stocks
                    )
                stocks_delta += system_stocks_delta

            try:
                item = self._GetInventoryItem(model)
            except errors.NotFoundError as e:
                # If item is not found, try getting frmo Opencart.
                try:
                    p = self._default_client.GetProduct(model)

                    item = InventoryItem(
                        model=p.model,
                        stocks=p.stocks,
                        last_sync_batch_id=self.sync_batch_id,
                    )
                except errors.NotFoundError as e:
                    logging.error("This item is not in the default client?: %s" % model)
                    continue

            item.stocks += stocks_delta
            if item.stocks <= 0:
                item.stocks = 0
            item.last_sync_batch_id = self.sync_batch_id

            if read_only:
                logging.info(
                    "Skip updating item %s %s: read-only mode"
                    % (item.model, item.stocks)
                )
                continue

            # Update self inventory.
            self._UpsertInventoryItem(item)

            # # Update external systems and inventory system cache.
            for system in self._external_systems:
                try:
                    self._UpdateExternalSystemItem(system, item)
                except errors.CommunicationError as e:
                    logging.error("Skipping external update due to error: " + str(e))
                except errors.NotFoundError as e:
                    logging.warn("Skipping external update: " + str(e))
                except errors.MultipleResultsError as e:
                    logging.warn("Skipping external update due to multiple: " + str(e))
