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

from errors import Error, NotFoundError, MultipleResultsError, CommunicationError, UnhandledTagError

_BASE_URL = 'https://partner.shopeemobile.com'


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


class ShopeeClient:
  """Implements a Shopee Client."""

  def __init__(self, shop_id, partner_id, partner_key):
    self._shop_id = shop_id
    self._partner_id = partner_id
    self._partner_key = partner_key
    self._products = []

    self.Refresh()

  def _ConstructPayload(self, input={}):
    input_copy = copy.deepcopy(input)
    input_copy['partner_id'] = self._partner_id
    input_copy['shopid'] = self._shop_id
    input_copy['timestamp'] = calendar.timegm(datetime.utcnow().utctimetuple())
    
    return json.dumps(input_copy)


  def _Request(self, endpoint, payload=''):
    domain = _BASE_URL + endpoint
    base_signature =  domain + '|' + payload
    signature = HMAC(self._partner_key, base_signature, sha256).hexdigest()
    headers = {
      'Content-Type': 'application/json',
      'Authorization': signature,
    }

    session = requests.Session()
    r = session.post(domain, headers=headers, data=payload)

    return json.loads(r.content)

  def Refresh(self):
    ENTRIES_PER_PAGE = 100
    offset = 0
    meta_items = []

    while True:
      result = self._Request('/api/v1/items/get', self._ConstructPayload({
        'pagination_entries_per_page': ENTRIES_PER_PAGE,
        'pagination_offset': offset,  
      }))
      meta_items.extend(result['items'])

      if result['more']:
        offset += ENTRIES_PER_PAGE
      else:
        break

    logging.info('Listing %d items...' % len(meta_items))

    items = []
    for meta_item in meta_items:
      item_id = meta_item['item_id']
      result = self._Request('/api/v1/item/get', self._ConstructPayload({
        'item_id': item_id  
      }))
      result = result['item']

      item = ShopeeProduct(
          item_id=result['item_id'], model=result['item_sku'], quantity=result['stock'])

      items.append(item)

      logging.info(
          'Loaded items: %d out of %d' % (len(items), len(meta_items)))

    self._products = items

  def GetProduct(self, model):
    """Returns a copy of a product detail.

    Args:
      model: string, The sku / model of the product being retrieved.

    Returns:
      ShopeeProduct, The product being searched.

    Raises:
      NotFoundError: The sku / model of the product is not in Lazada.
      MultipleResultsError: The sku / model is not unique in Lazada.
    """
    results = [p for p in self._products if p.model == model]
    if not results:
      raise NotFoundError('Not found in Shopee: %s' % model)
    if len(results) > 1:
      raise MultipleResultsError('Multiple results in Shopee: %s' % model)

    return copy.deepcopy(results[0])

  def ListProducts(self):
    """Returns a copy of internal dictionary."""
    return copy.deepcopy(self._products)

import pprint

if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)

  shop_id = 0
  partner_id = 0
  partner_key = ''

  client = ShopeeClient(shop_id, partner_id, partner_key)

  items = client.ListProducts()
  for item in items:
    pprint.pprint(item)

  # p = client.GetProduct('WHC0011RF')
  # logging.info('%s %d %d' % (p.model, p.quantity, p.stocks,))
