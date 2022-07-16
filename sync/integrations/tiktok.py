"""Package for retrieving and uploading product quantities to Tiktok."""

import copy
import hashlib
import hmac
import json
import logging
import time
import urllib
import requests

from sync.common.errors import (
    CommunicationError,
    NotFoundError,
    MultipleResultsError,
)

_OAUTH_AUTHORIZE_ENDPOINT = "/oauth/authorize"


class TiktokProduct(object):
    """Describes a Tiktok uploaded product."""

    def __init__(self, model, quantity=0, product_id="", sku_id=""):
        self.product_id = product_id
        self.sku_id = sku_id

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
        """Flag for when a Tiktok product's attribute has been modified."""
        return self._modified


class TiktokRequestResult:
    """Describes a request result from querying Tiktok."""

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


class TiktokClient:
    """Implements a Tiktok Client."""

    def __init__(
        self,
        domain,
        app_key,
        app_secret,
        access_token="",
        shop_id="",
        warehouse_id="",  # warehouse to stock from/to
        with_refresh=True,
    ):
        self._domain = domain
        self._app_key = app_key
        self._app_secret = app_secret
        self._access_token = access_token
        self._shop_id = shop_id
        self._products = []
        self._warehouse_id = warehouse_id

        if with_refresh:
            self.Refresh()

    @property
    def access_token(self):
        return self._access_token

    @access_token.setter
    def access_token(self, value):
        self._access_token = value

    def _Request(self, endpoint, payload={}, domain=None, raw=False, method=""):
        """Creates and sends a request to the given Tiktok action.

        Raises:
          CommunicationError: Cannot communicate properly with Tiktok.
        """

        if domain is None:
            domain = self._domain
        url = domain + endpoint

        query_params = {}
        query_params["timestamp"] = int(round(time.time()))
        query_params["app_key"] = self._app_key
        query_params["shop_id"] = self._shop_id

        # Signature
        # https://developers.tiktok-shops.com/documents/document/234136
        signature_base = "%s%s%s%s" % (
            self._app_secret,
            endpoint,
            str().join(f"{key}{query_params[key]}" for key in sorted(query_params)),
            self._app_secret,
        )
        signature = hmac.new(
            self._app_secret.encode(encoding="utf-8"),
            signature_base.encode(encoding="utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        # Only attach access token and sign after generating sign.
        query_params["access_token"] = self._access_token
        query_params["sign"] = signature

        encoded_url = f"{url}?{urllib.parse.urlencode(query_params)}"
        if payload:
            logging.info(str(payload))
            if method == "PUT":
                r = requests.put(
                    encoded_url,
                    json.dumps(payload),
                    headers={
                        "Content-Type": "application/json",
                    },
                )
            else:
                r = requests.post(
                    encoded_url,
                    json.dumps(payload),
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )
        else:
            r = requests.get(encoded_url)

        logging.info(r.text)

        if raw:
            res = r.text
        else:
            res = r.json()
        result = TiktokRequestResult(endpoint=endpoint, payload=payload, result=res)
        return result

    def Refresh(self):
        """Refreshes product records from Tiktok.

        Raises:
          CommunicationError: Cannot communicate properly with Tiktok.
        """

        # If warehouse id is not set, set warehouse to first warehouse_type=1.
        if not self._warehouse_id:
            r = self._Request("/api/logistics/get_warehouse_list")
            warehouses = [
                w
                for w in r.result.get("data").get("warehouse_list")
                if w.get("warehouse_type") == 1
            ]
            if len(warehouses) == 0:
                raise NotFoundError("no warehouses found")
            self._warehouse_id = warehouses[0].get("warehouse_id")

        logging.info(f"tiktok warehouse is set to: {self._warehouse_id}")

        page_number = 1
        page_size = 100
        items = []

        while True:
            r = self._Request(
                "/api/products/search",
                payload={"page_number": page_number, "page_size": page_size},
            )
            total_items = r.result.get("data").get("total", 0)

            # get items
            for product in r.result.get("data").get("products"):
                logging.info(product)
                product_id = product.get("id")
                for sku in product.get("skus"):
                    stocks = 0
                    for stock_info in sku.get("stock_infos"):
                        stocks += stock_info.get("available_stock", 0)

                    item = TiktokProduct(
                        model=sku.get("seller_sku"),
                        quantity=stocks,
                        product_id=product_id,
                        sku_id=sku.get("id"),
                    )

                    items.append(item)

            if page_number * page_size > total_items:
                break
            page_number += 1

        self._products = items

        return self

    def GetProductDirect(self, model):
        """Refreshes product records directly from Tiktok instead of consulting the map.

        Args:
          model: string, The sku of product being retrieved.

        Returns:
          TiktokProduct, The updated attributes of the product being retrieved.

        Raises:
          CommunicationError: Cannot communicate properly with Tiktok.
          NotFoundError: The sku / model of the product is not in Tiktok.
          MultipleResultsError: The sku / model is not unique in Tiktok.
        """

        raise CommunicationError("not yet implemented")

    def GetProduct(self, model):
        """Returns a copy of a product detail.

        Args:
          model: string, The sku / model of the product being retrieved.

        Returns:
          TiktokProduct, The product being searched.

        Raises:
          NotFoundError: The sku / model of the product is not in Tiktok.
          MultipleResultsError: The sku / model is not unique in Tiktok.
        """
        results = [p for p in self._products if p.model == model]
        if not results:
            raise NotFoundError("Not found in Tiktok: %s" % model)
        if len(results) > 1:
            raise MultipleResultsError("Multiple results in Tiktok: %s" % model)

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
          NotFoundError: The sku / model of the product is not in Tiktok.
          MultipleResultsError: The sku / model is not unique in Tiktok.
          CommunicationError: Cannot communicate properly with Tiktok.
        """
        product = self.GetProduct(model)
        product.stocks = stocks

        response = self.UpdateProducts([product])[0]

        return response

    def UpdateProducts(self, products):
        """Updates Tiktok records from the given list of products.

        Args:
          products: list<TiktokProduct>, The products with quantity changes to
              upload.

        Raises:
          CommunicationError: Cannot communicate properly with Tiktok.
        """
        results = []

        # https://developers.tiktok-shops.com/documents/document/237486
        for product in products:
            result = self._Request(
                "/api/products/stocks",
                {
                    "product_id": product.product_id,
                    # 'param is invalid ; detail:required param skus is missing'
                    "skus": [
                        {
                            "id": product.sku_id,
                            "stock_infos": [
                                {
                                    "warehouse_id": self._warehouse_id,
                                    "available_stock": product.quantity,
                                },
                            ],
                        },
                    ],
                },
                method="PUT",
            )
            results.append(result)

        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger().setLevel(logging.DEBUG)

    app_key = ""
    app_secret = ""
    warehouse_id = ""

    auth_domain = "https://auth.tiktok-shops.com"
    state = "errday"

    auth_url = (
        f"{auth_domain}{_OAUTH_AUTHORIZE_ENDPOINT}?app_key={app_key}&state={state}"
    )

    # auth_code = input(f"Open {auth_url} and input code: ")
    # auth_code = ""
    # logging.info(auth_code)

    # client = TiktokClient(auth_domain, app_key, app_secret, access_token)
    # r = client._Request(
    #     "/api/token/getAccessToken",
    #     {
    #         "app_key": app_key,
    #         "app_secret": app_secret,
    #         "auth_code": auth_code,
    #         "grant_type": "authorized_code",
    #     },
    #     raw=True,
    # )
    # logging.info(r.result)

    domain = "https://open-api.tiktokglobalshop.com"
    shop_id = ""
    # shop_id = ""
    access_token = ""
    client = TiktokClient(domain, app_key, app_secret, access_token, shop_id)
    for product in client._products:
        logging.info(f"{product.model}: {product.quantity}")

    logging.info(client.UpdateProductStocks("AE007", 2).result)
