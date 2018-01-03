"""Package for retrieving and uploading product quantities to Lazada."""

import copy
import logging
import requests
import string
import urllib
import xml.etree.ElementTree

from datetime import datetime
from hashlib import sha256
from hmac import HMAC

from errors import Error, NotFoundError, MultipleResultsError, CommunicationError, UnhandledTagError

_LIST_PRODUCTS_ACTION = 'GetProducts'

_UPDATE_PRODUCT_QUANTITY_ACTION = 'UpdatePriceQuantity'


class LazadaProduct(object):
    """Describes a Lazada uploaded product."""

    def __init__(self, model, quantity=0, reserved=0):
        self.model = model
        self.quantity = quantity
        self.reserved = reserved

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
            self, attachment=None, endpoint='', payload='', result=None, error_code=0,
            error_description=''):
        self.attachment = attachment
        self.endpoint = endpoint
        self.payload = payload

        self.result = result
        self.error_code = error_code
        self.error_description = error_description


class LazadaClient:
    """Implements a Lazada Client."""

    def __init__(self, domain, useremail, api_key, with_refresh=True):
        self._domain = domain
        self._useremail = useremail
        self._api_key = api_key
        self._products = []

        if with_refresh:
            self.Refresh()

    def _Request(self, action, payload='', offset=None, limit=None, search=None, body_xml_parser=None):
        """Creates and sends a request to the given Lazada action.

        Raises:
          CommunicationError: Cannot communicate properly with Lazada.
          UnhandledTagError: The result XML has an unhandled root XML tag.
        """

        parameters = {
            'UserID': self._useremail,
            'Version': '1.0',
            'Action': action,
            'Format': 'XML',
            'Timestamp': datetime.utcnow().isoformat()[:19]
        }
        if offset:
            parameters['Offset'] = offset
        if limit:
            parameters['Limit'] = limit
        if search:
            parameters['Search'] = search

        concatenated = urllib.urlencode(sorted(parameters.items()))
        parameters['Signature'] = HMAC(
            self._api_key, concatenated, sha256).hexdigest()
        concatenated = urllib.urlencode(sorted(parameters.items()))

        session = requests.Session()
        r = session.post(self._domain + concatenated, data=payload)
        try:
            e = xml.etree.ElementTree.fromstring(r.content)
        except xml.etree.ElementTree.ParseError:
            raise CommunicationError('Lazada returned a malformed response.')

        if e.tag == 'ErrorResponse':
            error_code = e.find('Head').find('ErrorCode').text
            error_description = e.find('Head').find('ErrorMessage').text

            result = LazadaRequestResult(
                endpoint=action, payload=payload, error_code=error_code,
                error_description=error_description)

            return result
        elif e.tag == 'SuccessResponse':
            if not body_xml_parser:
                parsed = list(e.find('Body'))
            else:
                parsed = body_xml_parser(e.find('Body'))

            result = LazadaRequestResult(
                endpoint=action, payload=payload, result=parsed)

            return result
        else:
            raise UnhandledTagError(
                'Unknown tag found in response: %s' % e.tag)

    def Refresh(self):
        """Refreshes product records from Lazada.

        Raises:
          CommunicationError: Cannot communicate properly with Lazada.
        """
        outer_scope = {'total': -1}
        offset = 0
        limit = 200
        items = []

        def xml_parser(body_xml_etree):
            outer_scope['total'] = int(
                body_xml_etree.find('TotalProducts').text)

            for product in body_xml_etree.find('Products').findall('Product'):
                sku = product.find('Skus').find('Sku')
                model = sku.find('SellerSku').text
                quantity = int(sku.find('quantity').text)
                reserved = quantity - \
                    int(sku.find('Available').text or quantity)

                item = LazadaProduct(
                    model=model, quantity=quantity, reserved=reserved)

                items.append(item)

        while True:
            result = self._Request(
                _LIST_PRODUCTS_ACTION, offset=offset, limit=limit,
                body_xml_parser=xml_parser)
            if result.error_code:
                raise CommunicationError(
                    'Error communicating: %s' % result.error_description)

            logging.info(
                'Loaded items: %d out of %d' % (len(items), outer_scope['total'],))

            offset += limit
            if offset >= outer_scope['total']:
                break

        logging.info('Total items: %d' % len(items))

        self._products = items

        return self

    def GetProductDirect(self, model):
        """Refreshes product records directly from Lazada instead of consulting the map.

        Args:
          model: string, The sku / model of the product being retrieved.

        Returns:
          Map, The product being searched.

        Raises:
          CommunicationError: Cannot communicate properly with Lazada.
          NotFoundError: The sku / model of the product is not in Lazada.
          MultipleResultsError: The sku / model is not unique in Lazada.
        """
        items = []

        def xml_parser(body_xml_etree):
            for product in body_xml_etree.find('Products').findall('Product'):
                sku = product.find('Skus').find('Sku')
                attrs = product.find('Attributes')

                images = []
                for img in sku.find('Images').findall('Image'):
                    if img.text:
                        imgurl = string.replace(img.text, 'catalog.jpg', 'zoom.jpg')
                        images.append(imgurl)

                p = {
                    'name': attrs.find('name').text,
                    'description': attrs.find('short_description').text,
                    'model': sku.find('SellerSku').text,
                    'stocks': int(sku.find('Available').text) or int(sku.find('quantity').text),
                    'price': float(sku.find('price').text),
                    'images': images,
                    'weight': float(sku.find('package_weight').text) or 0.9,
                    # 'category': 'PENDING',
                    # 'logistics': 'PENDING', # Not in lazada
                }
                items.append(p)

        result = self._Request(_LIST_PRODUCTS_ACTION,
                               search=model, body_xml_parser=xml_parser)
        if result.error_code:
            raise CommunicationError(
                'Error communicating: %s' % result.error_description)

        items = [x for x in items if x['model'] == model]
        if len(items) == 0:
            raise NotFoundError('No results for %s' % model)
        elif len(items) > 1:
            raise MultipleResultsError('Multiple results for %s' % model)

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
            raise NotFoundError('Not found in Lazada: %s' % model)
        if len(results) > 1:
            raise MultipleResultsError(
                'Multiple results in Lazada: %s' % model)

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
        """Updates Lazada records from the given list of products.

        Args:
          products: list<LazadaProduct>, The products with quantity changes to
              upload.

        Raises:
          CommunicationError: Cannot communicate properly with Lazada.
        """
        def _CreateUpdateProductPayload(model, quantity):
            request = xml.etree.ElementTree.Element('Request')
            product = xml.etree.ElementTree.SubElement(request, 'Product')
            skus = xml.etree.ElementTree.SubElement(product, 'Skus')
            sku = xml.etree.ElementTree.SubElement(skus, 'Sku')
            sku_seller_sku = xml.etree.ElementTree.SubElement(sku, 'SellerSku')
            sku_seller_sku.text = model
            sku_quantity = xml.etree.ElementTree.SubElement(sku, 'Quantity')
            sku_quantity.text = str(quantity)

            preamble = '<?xml version="1.0" encoding="utf-8" ?>'
            return preamble + xml.etree.ElementTree.tostring(request)

        results = []
        for p in products:
            if not p.modified:
                continue

            # Create XML request
            payload = _CreateUpdateProductPayload(p.model, p.quantity)

            result = self._Request(
                _UPDATE_PRODUCT_QUANTITY_ACTION, payload=payload)
            result.attachment = p

            results.append(result)

        return results


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    domain = 'https://api.sellercenter.lazada.com.ph?'
    useremail = ''
    api_key = ''

    client = LazadaClient(domain, useremail, api_key, with_refresh=False)

    p = client.GetProduct('WHC0011RF')
    logging.info('%s %d %d %d' % (p.model, p.quantity, p.reserved, p.stocks,))
