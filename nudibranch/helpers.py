import xml.sax.saxutils
from pyramid_addons.helpers import http_bad_request
from .exceptions import InvalidId
from .models import File


class DummyTemplateAttr(object):
    def __init__(self, default=None):
        self.default = default

    def __getattr__(self, attr):
        return self.default


def readlines(path):
    with open(path, 'r') as fh:
        return fh.read().splitlines()


def verify_file_ids(request, **kwargs):
    for name, item_id in kwargs.items():
        if item_id:
            item_file = File.fetch_by_id(item_id)
            if not item_file or item_file not in request.user.files:
                return http_bad_request(request, 'Invalid {0}'.format(name))
    return None


def escape(string):
    return xml.sax.saxutils.escape(string, {'"': "&quot;",
                                            "'": "&apos;"})

def fetch_request_ids(item_ids, cls, attr_name, verification_list=None):
    """Return a list of cls instances for all the ids provided in item_ids.

    :param item_ids: The list of ids to fetch objects for
    :param cls: The class to fetch the ids from
    :param attr_name: The name of the attribute for exception purposes
    :param verification_list: If provided, a list of acceptable instances

    Raise exception http_bad_request exception using attr_name if any do not
    exist, or are not present in the verification_list.

    """
    if not item_ids:
        return []
    items = []
    for item_id in item_ids:
        item = cls.fetch_by_id(item_id)
        if not item or (verification_list is not None and
                        item not in verification_list):
            raise InvalidId(attr_name)
        items.append(item)
    return items


def offset_from_sorted(item, lst, offset):
    '''Takes an item to look for, a sorted list, and an offset.
    If the item is in the list and the offset is valid, then it
    will return the item at that offset.  Returns None if the
    offset is out of bounds and IndexError if the given item isn't
    found.'''
    index = lst.index(item) + offset
    if index >= 0 and index < len(lst):
        return lst[index]


def next_in_sorted(item, lst):
    '''Returns the next item in the given (assumed sorted) list,
    or None if it is already the last item.  Throws an IndexError if
    it doesn't exist at all'''
    return offset_from_sorted(item, lst, 1)


def prev_in_sorted(item, lst):
    return offset_from_sorted(item, lst, -1)
