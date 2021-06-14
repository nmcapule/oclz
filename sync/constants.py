_SCRIPT_VERSION = "0.6"

_SYSTEM_OPENCART = "OPENCART"
_SYSTEM_LAZADA = "LAZADA"
_SYSTEM_SHOPEE = "SHOPEE"
_SYSTEM_WOOCOMMERCE = "WOOCOMMERCE"

_CONFIG_OPENCART = "Opencart"
_CONFIG_LAZADA = "Lazada"
_CONFIG_SHOPEE = "Shopee"
_CONFIG_WOOCOMMERCE = "WooCommerce"

_ERROR_SUCCESS = 0

_DEFAULT_DB_PATH = "./skeo_sync.db"

_CREATE_TABLE_OAUTH2 = """
CREATE TABLE IF NOT EXISTS oauth2 (
    system TEXT,
    access_token TEXT,
    refresh_token TEXT,
    created_on DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_on DATETIME
)
"""
_DROP_TABLE_OAUTH2 = """
DROP TABLE oauth2
"""

_CREATE_TABLE_SYNC_BATCH = """
CREATE TABLE IF NOT EXISTS sync_batch (
  sync_batch_id INTEGER PRIMARY KEY,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  script_version TEXT
)
"""
_DROP_TABLE_SYNC_BATCH = """
DROP TABLE sync_batch
"""

_CREATE_TABLE_SYNC_LOGS = """
CREATE TABLE IF NOT EXISTS sync_logs (
  sync_batch_id INTEGER,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  model TEXT,
  system TEXT,
  previous_stocks INTEGER,
  computed_stocks INTEGER,
  upload_error_code TEXT,
  upload_error_description TEXT
)
"""
_DROP_TABLE_SYNC_LOGS = """
DROP TABLE sync_logs
"""

_CREATE_TABLE_INVENTORY_SYSTEM_CACHE = """
CREATE TABLE IF NOT EXISTS inventory_system_cache (
  model TEXT,
  system TEXT,
  stocks INTEGER,
  last_sync_batch_id INTEGER,
  not_behaving INTEGER DEFAULT 0
)
"""
_DROP_TABLE_INVENTORY_SYSTEM_CACHE = """
DROP TABLE inventory_system_cache
"""

_CREATE_TABLE_INVENTORY_SYSTEM_CACHE_DELTA = """
CREATE TABLE IF NOT EXISTS inventory_system_cache_delta (
  model TEXT,
  system TEXT,
  cached_stocks INTEGER,
  current_stocks INTEGER,
  stocks_delta INTEGER,
  last_sync_batch_id INTEGER
)
"""
_DROP_TABLE_INVENTORY_SYSTEM_CACHE_DELTA = """
DROP TABLE inventory_system_cache_delta
"""

_CREATE_TABLE_INVENTORY = """
CREATE TABLE IF NOT EXISTS inventory (
  model TEXT PRIMARY KEY,
  stocks INTEGER,
  last_sync_batch_id INTEGER
)
"""
_DROP_TABLE_INVENTORY = """
DROP TABLE inventory
"""
