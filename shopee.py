"""Package for retrieving and uploading product quantities to Shopee."""

import calendar
import copy
import json
import logging
import requests
import urllib

from datetime import datetime
from hashlib import sha256
from hmac import HMAC

from errors import (
    Error,
    NotFoundError,
    MultipleResultsError,
    CommunicationError,
    UnhandledTagError,
)

_BASE_URL = "https://partner.shopeemobile.com"


class ShopeeProduct(object):
    """Describes a shopee uploaded product."""

    def __init__(self, item_id, model, quantity=0):
        self.item_id = item_id
        self.model = model
        self.quantity = quantity

        self._modified = False

    @property
    def stocks(self):
        """Getter for (available) stocks. Alias for quantity."""
        return self.quantity

    @stocks.setter
    def stocks(self, value):
        """Setter for (available) stocks."""
        self._modified = True
        self.quantity = value

    @property
    def modified(self):
        """Flag for when a Opencart product's attribute has been modified."""
        return self._modified


class ShopeeRequestResult:
    """Describes a request result from querying Shopee."""

    def __init__(
        self,
        attachment=None,
        endpoint="",
        payload="",
        result=None,
        error_code=0,
        error_description="",
    ):
        self.attachment = attachment
        self.endpoint = endpoint
        self.payload = payload

        self.result = result
        self.error_code = error_code
        self.error_description = error_description


class ShopeeClient:
    """Implements a Shopee Client."""

    def __init__(self, shop_id, partner_id, partner_key, with_refresh=True):
        self._shop_id = shop_id
        self._partner_id = partner_id
        self._partner_key = partner_key
        self._products = []

        if with_refresh:
            self.Refresh()

    def _ConstructPayload(self, input={}):
        input_copy = copy.deepcopy(input)
        input_copy["partner_id"] = self._partner_id
        input_copy["shopid"] = self._shop_id
        input_copy["timestamp"] = calendar.timegm(datetime.utcnow().utctimetuple())

        return json.dumps(input_copy)

    def _Request(self, endpoint, payload=""):
        domain = _BASE_URL + endpoint
        base_signature = domain + "|" + payload
        signature = HMAC(self._partner_key, base_signature, sha256).hexdigest()
        headers = {"Content-Type": "application/json", "Authorization": signature}

        session = requests.Session()
        r = session.post(domain, headers=headers, data=payload)

        # TODO(nmcapule): Handle value error - invalid JSON error.
        parsed = json.loads(r.content)

        if r.status_code >= 300 or ("error" in parsed and len(parsed["error"]) > 0):
            error_code = r.status_code
            error_description = parsed.get("msg", parsed.get("error", "request error"))

            return ShopeeRequestResult(
                endpoint=endpoint,
                payload=payload,
                error_code=error_code,
                error_description=error_description,
            )
        else:
            return ShopeeRequestResult(
                endpoint=endpoint, payload=payload, result=parsed
            )

    def Refresh(self):
        """Refreshes product records from Shopee.

        TODO(nmcapule): Handle communication error.
        Raises:
          CommunicationError: Cannot communicate properly with Shopee.
        """
        ENTRIES_PER_PAGE = 100
        offset = 0
        meta_items = []

        while True:
            result = self._Request(
                "/api/v1/items/get",
                self._ConstructPayload(
                    {
                        "pagination_entries_per_page": ENTRIES_PER_PAGE,
                        "pagination_offset": offset,
                    }
                ),
            )
            meta_items.extend(result.result["items"])

            if result.result["more"]:
                offset += ENTRIES_PER_PAGE
            else:
                break

        logging.info("Listing %d items..." % len(meta_items))

        items = []
        for meta_item in meta_items:
            item_id = meta_item["item_id"]

            for _ in range(10):
                try:
                    result = self._Request(
                        "/api/v1/item/get", self._ConstructPayload({"item_id": item_id})
                    )
                except ValueError as e:
                    logging.info(e)
                    continue

                # On success, break retry loop.
                logging.info("Success parsing %d" % item_id)
                break

            if not result.result:
                logging.info(
                    "Error loading %s: %s"
                    % (raw_item["item_sku"], result.error_description)
                )
                continue
            raw_item = result.result["item"]
            item = ShopeeProduct(
                item_id=raw_item["item_id"],
                model=raw_item["item_sku"],
                quantity=raw_item["stock"],
            )
            items.append(item)

            logging.info("Loaded items: %d out of %d" % (len(items), len(meta_items)))

        self._products = items

    def GetProduct(self, model):
        """Returns a copy of a product detail.

        Args:
          model: string, The sku / model of the product being retrieved.

        Returns:
          ShopeeProduct, The product being searched.

        Raises:
          NotFoundError: The sku / model of the product is not in Shopee.
          MultipleResultsError: The sku / model is not unique in Shopee.
        """
        results = [p for p in self._products if p.model == model]
        if not results:
            raise NotFoundError("Not found in Shopee: %s" % model)
        if len(results) > 1:
            raise MultipleResultsError("Multiple results in Shopee: %s" % model)

        return copy.deepcopy(results[0])

    def ListProducts(self):
        """Returns a copy of internal dictionary."""
        return copy.deepcopy(self._products)

    def UpdateProductStocks(self, model, stocks):
        """Updates a single products stock.

        Args:
          model: str, The sku / model of the product to be updated.
          stocks: int, The new number of stocks of the product.

        Raises:
          NotFoundError: The sku / model of the product is not in Shopee.
          MultipleResultsError: The sku / model is not unique in Shopee.
          CommunicationError: Cannot communicate properly with Shopee.
        """
        product = self.GetProduct(model)
        product.stocks = stocks

        return self.UpdateProducts([product])[0]

    def UpdateProducts(self, products):
        """Updates Shopee records from the given list of products.

        Args:
          products: list<ShopeeProduct>, The products with quantity changes to
              upload.

        Raises:
          CommunicationError: Cannot communicate properly with Shopee.
        """
        results = []
        for p in products:
            if not p.modified:
                continue

            # Create XML request
            result = self._Request(
                "/api/v1/items/update_stock",
                self._ConstructPayload({"item_id": p.item_id, "stock": p.stocks}),
            )
            result.attachment = p

            results.append(result)

        return results

    def CreateProduct(self, product):
        """Creates an entry for the product.

        Args:
          product: Object, The product to upload. Lifted from Lazada:
                {
                    'name': attrs.find('name').text,
                    'description': attrs.find('short_description').text,
                    'model': sku.find('SellerSku').text,
                    'stocks': int(sku.find('Available').text) or int(sku.find('quantity').text),
                    'price': float(sku.find('price').text),
                    'images': images,
                    'weight': float(sku.find('package_weight').text) or 0.5,
                }
        """
        result = self._Request(
            "/api/v1/item/add",
            self._ConstructPayload(
                {
                    "category_id": 5067,
                    "name": product["name"],
                    "description": product["description"],
                    "item_sku": product["model"],
                    "price": product["price"],
                    "stock": product["stocks"],
                    "weight": 0.2,  # product['weight'],
                    "images": [{"url": "https:%s" % img} for img in product["images"]],
                    "logistics": [
                        {
                            "logistic_id": 40013,  # Black Arrow Integrated
                            "enabled": True,  # Clear this up.
                            "size_id": 1,  # Small
                        }
                    ],
                }
            ),
        )

        if result.error_code:
            raise CommunicationError(
                "Error uploading product: %s" % result.error_description
            )

        return result.result["item_id"]


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    shop_id = 0
    partner_id = 0
    partner_key = ""

    client = ShopeeClient(shop_id, partner_id, partner_key)

    items = client.ListProducts()
    for item in items:
        logging.info(item)

    p = client.GetProduct("DFR0431")
    logging.info("%s %d %d" % (p.model, p.quantity, p.stocks))

    # Default CategoryID: 5067
    # Logistics: {u'logistic_name': u'Black Arrow Integrated', u'logistic_id': 40013}
