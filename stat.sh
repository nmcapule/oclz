SKEO_DB=/home/circtkeo/skeo_sync.db

echo ""
echo "========================================================================"
echo "========== Listing all stocks discrepancies in between systems"
echo "========================================================================"
echo ""

sqlite3 $SKEO_DB "
SELECT SUBSTR(oc.model || \"                              \", 1, 30),
       SUBSTR(IFNULL(oc.stocks, \"NO OC\") || \"     \", 1, 5) as oc,
       SUBSTR(IFNULL(lz.stocks, \"NO LZ\") || \"     \", 1, 5) as lz,
       SUBSTR(IFNULL(sh.stocks, \"NO SH\") || \"     \", 1, 5) as sh
FROM (SELECT model, stocks 
      FROM inventory_system_cache 
      WHERE system=\"OPENCART\") oc
LEFT JOIN (SELECT model, stocks 
      FROM inventory_system_cache 
      WHERE system=\"LAZADA\") lz
ON oc.model = lz.model
LEFT JOIN (SELECT model, stocks 
      FROM inventory_system_cache 
      WHERE system=\"SHOPEE\") sh
ON oc.model = sh.model
WHERE oc.stocks != lz.stocks
  OR oc.stocks != sh.stocks
  OR lz.stocks != sh.stocks
  OR oc.stocks IS NULL
  OR lz.stocks IS NULL
  OR sh.stocks IS NULL"

echo ""
echo "========================================================================"
echo "========== Listing all stocks discrepancies in between systems (uploaded items only)"
echo "========================================================================"
echo ""

sqlite3 $SKEO_DB "
SELECT SUBSTR(oc.model || \"                              \", 1, 30),
       SUBSTR(IFNULL(oc.stocks, \"NO OC\") || \"     \", 1, 5) as oc,
       SUBSTR(IFNULL(lz.stocks, \"NO LZ\") || \"     \", 1, 5) as lz,
       SUBSTR(IFNULL(sh.stocks, \"NO SH\") || \"     \", 1, 5) as sh
FROM (SELECT model, stocks 
      FROM inventory_system_cache 
      WHERE system=\"OPENCART\") oc
LEFT JOIN (SELECT model, stocks 
      FROM inventory_system_cache 
      WHERE system=\"LAZADA\") lz
ON oc.model = lz.model
LEFT JOIN (SELECT model, stocks 
      FROM inventory_system_cache 
      WHERE system=\"SHOPEE\") sh
ON oc.model = sh.model
WHERE oc.stocks != lz.stocks
  OR oc.stocks != sh.stocks
  OR lz.stocks != sh.stocks"

echo ""
echo "========================================================================"
echo "========== Listing all items in Lazada but not in Shopee"
echo "========================================================================"
echo ""

sqlite3 $SKEO_DB "
SELECT SUBSTR(oc.model || \"                              \", 1, 30),
       SUBSTR(IFNULL(oc.stocks, \"NO OC\") || \"     \", 1, 5) as oc,
       SUBSTR(IFNULL(lz.stocks, \"NO LZ\") || \"     \", 1, 5) as lz,
       SUBSTR(IFNULL(sh.stocks, \"NO SH\") || \"     \", 1, 5) as sh
FROM (SELECT model, stocks 
      FROM inventory_system_cache 
      WHERE system=\"OPENCART\") oc
LEFT JOIN (SELECT model, stocks 
      FROM inventory_system_cache 
      WHERE system=\"LAZADA\") lz
ON oc.model = lz.model
LEFT JOIN (SELECT model, stocks 
      FROM inventory_system_cache 
      WHERE system=\"SHOPEE\") sh
ON oc.model = sh.model
WHERE lz.stocks IS NOT NULL
  AND sh.stocks IS NULL"
