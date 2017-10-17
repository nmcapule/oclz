"""Package for retrieving and uploading product quantities to Opencart."""

import copy
import json
import logging
import requests

from errors import Error, NotFoundError, MultipleResultsError, CommunicationError

_LIST_PRODUCTS_ENDPOINT = 'module/store_sync/listlocalproducts'

# TODO(nmcapule): Endpoint
_UPDATE_PRODUCT_QUANTITY_ENDPOINT = 'module/store_sync/setlocalquantity'


class OpencartProduct(object):
  """Describes a Opencart uploaded product."""

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
    """Flag for when a Opencart product's attribute has been modified."""
    return self._modified


class OpencartRequestResult:
  """Describes a request result from querying Opencart."""

  def __init__(
      self, attachment=None, endpoint='', payload='', result=None, error_code=0,
      error_description=''):
    self.attachment = attachment
    self.endpoint = endpoint
    self.payload = payload

    self.result = result
    self.error_code = error_code
    self.error_description = error_description


class OpencartClient:
  """Implements a Opencart Client."""

  def __init__(self, domain, username, password):
    self._domain = domain
    self._username = username
    self._password = password
    self._products = []

    self.Refresh()

  def _Request(self, endpoint, payload='', content_parser=None):
    """Creates and sends a request to the given Opencart endpoint.

    Args:
      endpoint: str, The endpoint to send the request.
      payload: any, Parameter arguments.

    Returns:
      OpencartRequestResult, The formatted response.

    Raises:
      CommunicationError: Cannot communicate properly with Opencart.
    """
    if payload:
      payload = '&' + payload
    params = {
        'username': self._username,
        'password': self._password,
        'redirect': '{0}{1}{2}'.format(self._domain, endpoint, payload)
    }
    session = requests.Session()
    r = session.post(self._domain + "common/login", data=params)

    error_code = 0
    error_description = 'SUCCESS'

    result = OpencartRequestResult(
        endpoint=endpoint, payload=payload, error_code=error_code,
        error_description=error_description)
    if not content_parser:
      result.result = r.content
    else:
      result.result = content_parser(r.content)

    return result

  def Refresh(self):
    """Refreshes product records from Opencart.

    Raises:
      CommunicationError: Cannot communicate properly with Opencart.
    """
    items = []

    def content_parser(str):
      json_stub = json.loads(str)
      for json_product in json_stub:
        item = OpencartProduct(
            model=json_product['model'],
            quantity=int(json_product['quantity']))
        items.append(item)

    result = self._Request(
        _LIST_PRODUCTS_ENDPOINT, content_parser=content_parser)

    if not items:
      raise CommunicationError('Somehow, zero items retrieved from Opencart!')

    self._products = items

    return self

  def GetProduct(self, model):
    """Returns a copy of a product detail.

    Args:
      model: string, The sku / model of the product being retrieved.

    Raises:
      NotFoundError: The sku / model of the product is not in Opencart.
      MultipleResultsError: The sku / model is not unique in Opencart.
    """
    results = [p for p in self._products if p.model == model]
    if not results:
      raise NotFoundError('Not found in Opencart: %s' % model)
    if len(results) > 1:
      logging.error('Multiple results in Opencart: %s' % model)
      # raise MultipleResultsError('Multiple results in Opencart: %s' % model)

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
      NotFoundError: The sku / model of the product is not in Opencart.
      MultipleResultsError: The sku / model is not unique in Opencart.
      CommunicationError: Cannot communicate properly with Opencart.
    """
    product = self.GetProduct(model)
    product.stocks = stocks

    return self.UpdateProducts([product])[0]

  def UpdateProducts(self, products):
    """Updates Opencart records from the given list of products.

    Args:
      products: list<OpencartProduct>, The products with quantity changes to
          upload.

    Raises:
      CommunicationError: Cannot communicate properly with Opencart
    """
    def _CreateUpdateProductPayload(model, quantity):
      return 'model=%s&quantity=%s' % (model, quantity,)

    results = []
    for p in products:
      if not p.modified:
        continue

      payload = _CreateUpdateProductPayload(p.model, p.quantity)

      result = self._Request(_UPDATE_PRODUCT_QUANTITY_ENDPOINT, payload)
      result.attachment = p

      results.append(result)

    return results


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)

  domain = 'https://circuit.rocks/admin/index.php?route='
  username = ''
  password = ''

  client = OpencartClient(domain, username, password)

  p = client.GetProduct('WHC0011RF')
  logging.info('%s %d %d' % (p.model, p.quantity, p.stocks,))
