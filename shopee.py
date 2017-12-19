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
    base_signature = _BASE_URL + endpoint + '|' + payload
    signature = HMAC(self._partner_key, base_signature, sha256).hexdigest()

    print(payload)
    print(base_signature)
    print(signature)

    return

  def Refresh(self):
    pass


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)

  shop_id = ''
  partner_id = ''
  partner_key = ''

  client = ShopeeClient(shop_id, partner_id, partner_key)
  client._Request('/api/shopao', client._ConstructPayload({'no more': 2}))

  # p = client.GetProduct('WHC0011RF')
  # logging.info('%s %d %d' % (p.model, p.quantity, p.stocks,))
