import copy
import json
import logging

from woocommerce import API
from sync.common.errors import (
    NotFoundError,
    MultipleResultsError,
    CommunicationError,
)


class WooCommerceProduct(object):
    """Describes a WooCommerce uploaded product."""

    def __init__(self, model, quantity=0):
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
        """Flag for when a WooCommerce product's attribute has been modified."""
        return self._modified


class WooCommerceRequestResult:
    """Describes a request result from querying WooCommerce."""

    def __init__(
        self,
        attachment=None,
        endpoint="",
        payload="",
        result=None,
        error_code=0,
        error_description="",
        headers={},
    ):
        self.attachment = attachment
        self.endpoint = endpoint
        self.payload = payload

        self.result = result
        self.error_code = error_code
        self.error_description = error_description
        self.headers = headers


class WooCommerceClient:
    """Implements and wraps a WooCommerce Client.

    For reference, check out:
    https://docs.woocommerce.com/document/woocommerce-rest-api/
    """

    def __init__(self, domain, consumer_key, consumer_secret):
        self._domain = domain
        self._consumer_key = consumer_key
        self._consumer_secret = consumer_secret
        self._products = []

        self._wrapped_client = API(
            url=self._domain,
            consumer_key=self._consumer_key,
            consumer_secret=self._consumer_secret,
            version="wc/v3",
        )

        self.Refresh()

    def _Request(self, resource, payload=None, params={}, method="GET"):
        """Creates and sends a request to the given WooCommerce resource.

        Args:
          resource: str, The resource to send the request.
          payload: any, Data payload.
          params: dict, Parameter arguments.
          method: str, HTTP method to use: GET|POST|PUT.

        Returns:
          WooCommerceRequestResult, The formatted response.

        Raises:
          CommunicationError: Cannot communicate properly with WooCommerce.
        """
        if method == "POST":
            r = self._wrapped_client.post(resource, data=payload, params=params)
        elif method == "PUT":
            r = self._wrapped_client.put(resource, data=payload, params=params)
        else:
            r = self._wrapped_client.get(resource, params=params)

        headers = r.headers
        parsed = r.json()
        if r.status_code >= 300:
            error_code = parsed.get("code", "unknown_error_code")
            error_description = parsed.get("message", "generic error")

            return WooCommerceRequestResult(
                endpoint=resource,
                payload=payload,
                error_code=error_code,
                error_description=error_description,
                headers=headers,
            )
        else:
            return WooCommerceRequestResult(
                endpoint=resource,
                payload=payload,
                result=parsed,
                headers=headers,
            )

    def Refresh(self):
        """Refreshes products from WooCommerce."""
        total_pages = 999
        per_page = 100
        page = 1
        items = []

        while True:
            result = self._Request(
                resource="products",
                params={
                    "per_page": per_page,
                    "page": page,
                },
            )
            total_pages = int(result.headers["X-WP-TotalPages"])
            page = page + 1

            for product in result.result:
                model = product["sku"]
                quantity = product["stock_quantity"]

                if not model or quantity is None:
                    logging.info(
                        "Skipping item %s: sku=%s, quantity=%s"
                        % (product["id"], model, quantity)
                    )
                    continue

                item = WooCommerceProduct(model, quantity)
                items.append(item)

            if page > total_pages:
                break

        self._products = items

    def GetProduct(self, model):
        """Returns a copy of a product detail.

        Args:
          model: string, The sku / model of the product being retrieved.

        Returns:
          WooCommerceProduct, The product being searched.

        Raises:
          NotFoundError: The sku / model of the product is not in WooCommerce.
          MultipleResultsError: The sku / model is not unique in WooCommerce.
        """
        results = [p for p in self._products if p.model == model]
        if not results:
            raise NotFoundError("Not found in WooCommerce: %s" % model)
        if len(results) > 1:
            raise MultipleResultsError("Multiple results in WooCommerce: %s" % model)

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

        return self.UpdateProducts([product])[0]

    def UpdateProducts(self, products):
        """Updates WooCommerce records from the given list of products.

        Args:
          products: list<WooCommerceProduct>, The products with quantity changes to
              upload.

        Raises:
          CommunicationError: Cannot communicate properly with WooCommerce.
        """
        results = []
        for product in products:
            if not product.modified:
                continue

            result = self._Request(
                f"products/{product.id}",
                payload={
                    "stock_quantity": product.quantity,
                },
                method="PUT",
            )
            result.attachment = product

            results.append(result)

        return results
