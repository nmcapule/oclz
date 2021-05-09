"""Package for retrieving and uploading product quantities to Lazada."""

import copy
import hashlib
import hmac
import logging
import requests
import string
import time
import urllib
import xml.etree.ElementTree

from hashlib import sha256

from sync.common.errors import (
    Error,
    NotFoundError,
    MultipleResultsError,
    CommunicationError,
    UnhandledTagError,
)


class LazadaProduct(object):
    """Describes a Lazada uploaded product."""

    def __init__(self, model, quantity=0, reserved=0, item_id="", sku_id=""):
        self.model = model
        self.quantity = quantity
        self.reserved = reserved

        self.item_id = item_id
        self.sku_id = sku_id

        self._modified = False

    @property
    def stocks(self):
        """Getter for (available) stocks. `stocks = quantity - reserved`"""
        return self.quantity - self.reserved

    @stocks.setter
    def stocks(self, value):
        """Setter for (available) stocks."""
        self._modified = True
        self.quantity = value + self.reserved

    @property
    def modified(self):
        """Flag for when a Lazada product's attribute has been modified."""
        return self._modified


class LazadaRequestResult:
    """Describes a request result from querying Lazada."""

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


def sign(secret, api, parameters):
    concatenated = "%s%s" % (
        api,
        str().join("%s%s" % (key, parameters[key]) for key in sorted(parameters)),
    )

    h = hmac.new(
        secret.encode(encoding="utf-8"),
        concatenated.encode(encoding="utf-8"),
        digestmod=hashlib.sha256,
    )

    return h.hexdigest().upper()


class LazadaClient:
    """Implements a Lazada Client."""

    def __init__(
        self,
        domain,
        app_key,
        app_secret,
        access_token="",
        with_refresh=True,
        with_confirm=True,
    ):
        self._domain = domain
        self._app_key = app_key
        self._app_secret = app_secret
        self._access_token = access_token
        self._products = []

        # Set to true to reconfirm from Lazada when doing an item quantity update.
        self._with_confirm = with_confirm

        if with_refresh:
            self.Refresh()

    @property
    def access_token(self):
        return self._access_token

    @access_token.setter
    def access_token(self, value):
        self._access_token = value

    def _Request(self, endpoint, api_parameters={}, payload="", domain=None, raw=False):
        """Creates and sends a request to the given Lazada action.

        Raises:
          CommunicationError: Cannot communicate properly with Lazada.
          UnhandledTagError: The result XML has an unhandled root XML tag.
        """

        parameters = {
            "app_key": self._app_key,
            "sign_method": "sha256",
            "timestamp": str(int(round(time.time()))) + "000",
            "partner_id": "lazop-sdk-python-20180424",
        }
        if self._access_token and not raw:
            parameters["access_token"] = self._access_token
        if payload:
            parameters["payload"] = payload
        parameters.update(api_parameters)
        parameters["sign"] = sign(self._app_secret, endpoint, parameters)

        if domain is None:
            domain = self._domain
        url = domain + endpoint

        # urllib.urlencode(sorted(parameters.items()))

        if payload:
            r = requests.post(url, parameters)
        else:
            r = requests.get(url, parameters)

        res = r.json()
        if "code" in res and res["code"] != "0":
            error_code = res["code"]
            error_description = res["message"]

            result = LazadaRequestResult(
                endpoint=endpoint,
                payload=payload,
                error_code=error_code,
                error_description=error_description,
            )

            return result
        else:
            if raw:
                result = LazadaRequestResult(
                    endpoint=endpoint, payload=payload, result=res
                )
            else:
                result = LazadaRequestResult(
                    endpoint=endpoint, payload=payload, result=res.get("data", "")
                )

            return result

    def Refresh(self):
        """Refreshes product records from Lazada.

        Raises:
          CommunicationError: Cannot communicate properly with Lazada.
        """
        outer_scope = {"total": 0}
        offset = 0
        limit = 50
        items = []

        def data_parser(data):
            outer_scope["total"] = data["total_products"]

            for product in data["products"]:
                for sku in product["skus"]:
                    model = sku["SellerSku"]
                    quantity = int(sku["quantity"])

                    # Looks like Lazada ditched the "Available" keyword :P
                    reserved = quantity - int(sku.get("Available", quantity))

                    # New required fields in product update.
                    item_id = product["item_id"]
                    sku_id = sku["SkuId"]

                    item = LazadaProduct(
                        model=model,
                        quantity=quantity,
                        reserved=reserved,
                        item_id=item_id,
                        sku_id=sku_id,
                    )

                    items.append(item)

        while True:
            parameters = {"offset": offset, "limit": limit}
            result = self._Request("/products/get", parameters)
            if result.error_code:
                raise CommunicationError(
                    "Error communicating: %s" % result.error_description
                )

            data_parser(result.result)

            logging.info(
                "Loaded items: %d out of %d" % (len(items), outer_scope["total"])
            )

            offset += limit
            if offset >= outer_scope["total"]:
                break

        logging.info("Total items: %d" % len(items))

        self._products = items

        return self

    def GetProductDirect(self, model):
        """Refreshes product records directly from Lazada instead of consulting the map.

        Args:
          model: string, The sku of product being retrieved.

        Returns:
          LazadaProduct, The updated attributes of the product being retrieved.

        Raises:
          CommunicationError: Cannot communicate properly with Lazada.
          NotFoundError: The sku / model of the product is not in Lazada.
          MultipleResultsError: The sku / model is not unique in Lazada.
        """
        items = []

        def data_parser(data):
            for product in data["products"]:
                for sku in product["skus"]:
                    model = sku["SellerSku"]
                    quantity = int(sku["quantity"])

                    # Looks like Lazada ditched the "Available" keyword :P
                    reserved = quantity - int(sku.get("Available", quantity))

                    # New required fields in product update.
                    item_id = product["item_id"]
                    sku_id = sku["SkuId"]

                    item = LazadaProduct(
                        model=model,
                        quantity=quantity,
                        reserved=reserved,
                        item_id=item_id,
                        sku_id=sku_id,
                    )

                    items.append(item)

        result = self._Request("/products/get", {"search": model})
        if result.error_code:
            raise CommunicationError(
                "Error communicating: %s" % result.error_description
            )

        data_parser(result.result)

        items = [x for x in items if x.model == model]
        if len(items) == 0:
            raise NotFoundError("No results for %s" % model)
        elif len(items) > 1:
            logging.warn("Lazada has multiple results for %s ... carry on." % model)
            # raise MultipleResultsError("Multiple results for %s" % model)

        return items[0]

    def GetProduct(self, model):
        """Returns a copy of a product detail.

        Args:
          model: string, The sku / model of the product being retrieved.

        Returns:
          LazadaProduct, The product being searched.

        Raises:
          NotFoundError: The sku / model of the product is not in Lazada.
          MultipleResultsError: The sku / model is not unique in Lazada.
        """
        results = [p for p in self._products if p.model == model]
        if not results:
            raise NotFoundError("Not found in Lazada: %s" % model)
        if len(results) > 1:
            raise MultipleResultsError("Multiple results in Lazada: %s" % model)

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
          NotFoundError: The sku / model of the product is not in Lazada.
          MultipleResultsError: The sku / model is not unique in Lazada.
          CommunicationError: Cannot communicate properly with Lazada.
        """
        product = self.GetProduct(model)
        product.stocks = stocks

        response = self.UpdateProducts([product])[0]
        
        if self._with_confirm:
            updated = self.GetProductDirect(model)
            if updated.stocks != product.stocks:
                raise CommunicationError("Product was not updated correctly in Lazada %s" % product.model)

        return response

    def UpdateProducts(self, products):
        """Updates Lazada records from the given list of products.

        Args:
          products: list<LazadaProduct>, The products with quantity changes to
              upload.

        Raises:
          CommunicationError: Cannot communicate properly with Lazada.
        """

        def _CreateUpdateProductPayload(model, quantity, item_id="", sku_id=""):
            request = xml.etree.ElementTree.Element("Request")
            product = xml.etree.ElementTree.SubElement(request, "Product")
            skus = xml.etree.ElementTree.SubElement(product, "Skus")
            sku = xml.etree.ElementTree.SubElement(skus, "Sku")

            sku_seller_sku = xml.etree.ElementTree.SubElement(sku, "SellerSku")
            sku_seller_sku.text = model
            sku_quantity = xml.etree.ElementTree.SubElement(sku, "Quantity")
            sku_quantity.text = str(quantity)

            # New fields from https://open.lazada.com/doc/doc.htm?spm=a2o9m.11193494.0.0.1c95266bK3UTnL#?nodeId=11207&docId=108479
            item_id = xml.etree.ElementTree.SubElement(sku, "ItemId")
            item_id.text = item_id
            sku_id = xml.etree.ElementTree.SubElement(sku, "SkuId")
            sku_id.text = sku_id

            preamble = '<?xml version="1.0" encoding="utf-8" ?>'

            # tostring returns bytes. Weird huh?
            content = xml.etree.ElementTree.tostring(request)
            if isinstance(content, (bytes, bytearray)):
                content = str(content, "UTF-8")

            return preamble + content

        results = []
        for p in products:
            if not p.modified:
                continue

            # Create XML request
            payload = _CreateUpdateProductPayload(
                p.model, p.quantity, item_id=p.item_id, sku_id=p.sku_id
            )
            result = self._Request("/product/price_quantity/update", payload=payload)
            result.attachment = p

            results.append(result)

        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    domain = "https://api.lazada.com.ph/rest"
    app_key = 102505
    app_secret = ""
    access_token = ""

    client = LazadaClient(domain, app_key, app_secret, access_token=access_token)

    p = client.GetProduct("WHC0011RF")
    logging.info("%s %d %d %d" % (p.model, p.quantity, p.reserved, p.stocks))

    r = client.UpdateProductStocks("WHC0011RF", 4)
    logging.info("%s %s" % (r.error_code, r.error_description))
