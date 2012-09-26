import transaction
import unittest
from chameleon.zpt.template import Macro
from nudibranch import add_routes
from nudibranch.models import Class, Session, User, initialize_sql
from nudibranch.views import (class_create, class_edit, class_list, class_view,
                              home, session_create, project_edit, session_edit,
                              user_class_join, user_create, user_edit,
                              user_list, user_view)
from pyramid import testing
from pyramid.httpexceptions import (HTTPBadRequest, HTTPConflict, HTTPCreated,
                                    HTTPNotFound, HTTPOk)
from pyramid.url import route_path
from sqlalchemy import create_engine


def _init_testing_db():
    """Create an in-memory database for testing."""
    engine = create_engine('sqlite://')
    initialize_sql(engine)

    items = [Class(name='Test 101'),
             User(email='', name='User', username='user1', password='pswd1')]
    Session.add_all(items)


class BaseAPITest(unittest.TestCase):
    """Base test class for all API method (or controller) tests."""

    def make_request(self, **kwargs):
        """Build the request object used in view tests."""
        kwargs.setdefault('user', None)
        request = testing.DummyRequest(**kwargs)
        return request

    def setUp(self):
        """Initialize the database and add routes."""
        self.config = testing.setUp()
        _init_testing_db()
        add_routes(self.config)

    def tearDown(self):
        """Destroy the session and end the pyramid testing."""
        testing.tearDown()
        transaction.abort()
        Session.remove()


class BasicTests(BaseAPITest):
    def test_site_layout_decorator(self):
        request = self.make_request()
        info = home(request)
        self.assertIsInstance(info['_LAYOUT'], Macro)
        self.assertRaises(ValueError, info['_S'], 'favicon.ico')

    def test_home(self):
        request = self.make_request()
        info = home(request)
        self.assertEqual('Home', info['page_title'])


class ClassTests(BaseAPITest):
    """The the API methods involved with modifying class information."""

    def test_class_create_duplicate_name(self):
        json_data = {'name': 'Test 101'}
        request = self.make_request(json_body=json_data)
        info = class_create(request)
        self.assertEqual(HTTPConflict.code, request.response.status_code)
        self.assertEqual('Class \'Test 101\' already exists', info['message'])

    def test_class_create_invalid_name(self):
        json_data = {}
        for item in ['', 'a' * 2]:
            json_data['name'] = item
            request = self.make_request(json_body=json_data)
            info = class_create(request)
            self.assertEqual(HTTPBadRequest.code, request.response.status_code)
            self.assertEqual('Invalid request', info['error'])
            self.assertEqual(1, len(info['messages']))

    def test_class_create_no_params(self):
        request = self.make_request(json_body={})
        info = class_create(request)
        self.assertEqual(HTTPBadRequest.code, request.response.status_code)
        self.assertEqual('Invalid request', info['error'])
        self.assertEqual(1, len(info['messages']))

    def test_class_create_valid(self):
        json_data = {'name': 'Foobar'}
        request = self.make_request(json_body=json_data)
        info = class_create(request)
        self.assertEqual(HTTPCreated.code, request.response.status_code)
        self.assertEqual(route_path('class', request), info['redir_location'])
        name = json_data['name']
        klass = Session.query(Class).filter_by(name=name).first()
        self.assertEqual(json_data['name'], klass.name)

    def test_class_edit(self):
        request = self.make_request()
        info = class_edit(request)
        self.assertEqual(HTTPOk.code, request.response.status_code)
        self.assertEqual('Create Class', info['page_title'])

    def test_class_list(self):
        request = self.make_request()
        info = class_list(request)
        self.assertEqual(HTTPOk.code, request.response.status_code)
        self.assertEqual(1, len(info['classes']))
        self.assertEqual('Test 101', info['classes'][0].name)

    def test_class_view(self):
        request = self.make_request(matchdict={'class_name': 'Test 101'})
        info = class_view(request)
        self.assertEqual(HTTPOk.code, request.response.status_code)
        self.assertEqual('Test 101', info['klass'].name)

    def test_class_view_invalid(self):
        request = self.make_request(matchdict={'class_name': 'Test Invalid'})
        info = class_view(request)
        self.assertIsInstance(info, HTTPNotFound)


class ClassJoinTests(BaseAPITest):
    """Test the API methods involved in joining a class."""
    def test_invalid_user(self):
        user = Session.query(User).filter_by(username='user1').first()
        request = self.make_request(json_body={}, user=user,
                                    matchdict={'class_name': 'Test 101',
                                               'username': 'admin'})
        info = user_class_join(request)
        self.assertEqual(HTTPBadRequest.code, request.response.status_code)
        self.assertEqual('Invalid user', info['messages'])

    def test_invalid_class(self):
        user = Session.query(User).filter_by(username='user1').first()
        request = self.make_request(json_body={}, user=user,
                                    matchdict={'class_name': 'Test Invalid',
                                               'username': 'user1'})
        info = user_class_join(request)
        self.assertEqual(HTTPBadRequest.code, request.response.status_code)
        self.assertEqual('Invalid class', info['messages'])

    def test_valid(self):
        user = Session.query(User).filter_by(username='user1').first()
        request = self.make_request(json_body={}, user=user,
                                    matchdict={'class_name': 'Test 101',
                                               'username': 'user1'})
        info = user_class_join(request)
        self.assertEqual(HTTPOk.code, request.response.status_code)
        self.assertEqual('Class joined', info['message'])


class ProjectTests(BaseAPITest):
    def test_project_edit(self):
        klass = Session.query(Class).first()
        request = self.make_request(matchdict={'class_name': klass.name})
        info = project_edit(request)
        self.assertEqual(HTTPOk.code, request.response.status_code)
        self.assertEqual('Create Project', info['page_title'])
        self.assertEqual(klass.id, info['class_id'])


class SessionTests(BaseAPITest):
    """Test the API methods involved in session creation and destruction."""

    def test_session_create_invalid(self):
        request = self.make_request(json_body={'username': 'user1',
                                               'password': 'badpw'})
        info = session_create(request)
        self.assertEqual(HTTPConflict.code, request.response.status_code)
        self.assertEqual('Invalid login', info['message'])

    def test_session_create_no_params(self):
        request = self.make_request(json_body={})
        info = session_create(request)
        self.assertEqual(HTTPBadRequest.code, request.response.status_code)
        self.assertEqual('Invalid request', info['error'])
        self.assertEqual(2, len(info['messages']))

    def test_session_create_no_password(self):
        request = self.make_request(json_body={'username': 'foo'})
        info = session_create(request)
        self.assertEqual(HTTPBadRequest.code, request.response.status_code)
        self.assertEqual('Invalid request', info['error'])
        self.assertEqual(1, len(info['messages']))

    def test_session_create_no_username(self):
        request = self.make_request(json_body={'password': 'bar'})
        info = session_create(request)
        self.assertEqual(HTTPBadRequest.code, request.response.status_code)
        self.assertEqual('Invalid request', info['error'])
        self.assertEqual(1, len(info['messages']))

    def test_session_create_valid(self):
        request = self.make_request(json_body={'username': 'user1',
                                               'password': 'pswd1'})
        info = session_create(request)
        self.assertEqual(HTTPCreated.code, request.response.status_code)
        self.assertEqual(route_path('user_item', request, username='user1'),
                         info['redir_location'])

    def test_session_edit(self):
        request = self.make_request()
        info = session_edit(request)
        self.assertEqual(HTTPOk.code, request.response.status_code)
        self.assertEqual('Login', info['page_title'])


class UserTests(BaseAPITest):
    """The the API methods involved with modifying user information."""

    def test_user_create_duplicate_name(self):
        json_data = {'email': 'foo@bar.com', 'name': 'Foobar',
                     'password': 'Foobar', 'username': 'user1'}
        request = self.make_request(json_body=json_data)
        info = user_create(request)
        self.assertEqual(HTTPConflict.code, request.response.status_code)
        self.assertEqual('Username \'user1\' already exists', info['message'])

    def test_user_create_invalid_email(self):
        json_data = {'name': 'Foobar', 'password': 'Foobar',
                     'username': 'foobar'}
        for item in ['', 'a' * 5]:
            json_data['email'] = item
            request = self.make_request(json_body=json_data)
            info = user_create(request)
            self.assertEqual(HTTPBadRequest.code, request.response.status_code)
            self.assertEqual('Invalid request', info['error'])
            self.assertEqual(1, len(info['messages']))

    def test_user_create_invalid_name(self):
        json_data = {'email': 'foo@bar.com', 'password': 'Foobar',
                     'username': 'foobar'}
        for item in ['', 'a' * 2]:
            json_data['name'] = item
            request = self.make_request(json_body=json_data)
            info = user_create(request)
            self.assertEqual(HTTPBadRequest.code, request.response.status_code)
            self.assertEqual('Invalid request', info['error'])
            self.assertEqual(1, len(info['messages']))

    def test_user_create_invalid_password(self):
        json_data = {'email': 'foo@bar.com', 'name': 'Foobar',
                     'username': 'foobar'}
        for item in ['', 'a' * 5]:
            json_data['password'] = item
            request = self.make_request(json_body=json_data)
            info = user_create(request)
            self.assertEqual(HTTPBadRequest.code, request.response.status_code)
            self.assertEqual('Invalid request', info['error'])
            self.assertEqual(1, len(info['messages']))

    def test_user_create_invalid_username(self):
        json_data = {'email': 'foo@bar.com', 'name': 'Foobar',
                     'password': 'foobar'}
        for item in ['', 'a' * 2, 'a' * 17]:
            json_data['username'] = item
            request = self.make_request(json_body=json_data)
            info = user_create(request)
            self.assertEqual(HTTPBadRequest.code, request.response.status_code)
            self.assertEqual('Invalid request', info['error'])
            self.assertEqual(1, len(info['messages']))

    def test_user_create_no_params(self):
        request = self.make_request(json_body={})
        info = user_create(request)
        self.assertEqual(HTTPBadRequest.code, request.response.status_code)
        self.assertEqual('Invalid request', info['error'])
        self.assertEqual(4, len(info['messages']))

    def test_user_create_valid(self):
        json_data = {'email': 'foo@bar.com', 'name': 'Foobar',
                     'password': 'Foobar', 'username': 'user2'}
        request = self.make_request(json_body=json_data)
        info = user_create(request)
        self.assertEqual(HTTPCreated.code, request.response.status_code)
        expected = route_path('session', request, _query={'username': 'user2'})
        self.assertEqual(expected, info['redir_location'])
        username = json_data['username']
        user = Session.query(User).filter_by(username=username).first()
        self.assertEqual(json_data['email'], user.email)
        self.assertEqual(json_data['name'], user.name)
        self.assertNotEqual(json_data['password'], user._password)

    def test_user_edit(self):
        request = self.make_request()
        info = user_edit(request)
        self.assertEqual(HTTPOk.code, request.response.status_code)
        self.assertEqual('Create User', info['page_title'])

    def test_user_list(self):
        request = self.make_request()
        info = user_list(request)
        self.assertEqual(HTTPOk.code, request.response.status_code)
        self.assertEqual(1, len(info['users']))
        self.assertEqual('user1', info['users'][0].username)

    def test_user_view(self):
        request = self.make_request(matchdict={'username': 'user1'})
        info = user_view(request)
        self.assertEqual(HTTPOk.code, request.response.status_code)
        self.assertEqual('user1', info['user'].username)

    def test_user_view_invalid(self):
        request = self.make_request(matchdict={'username': 'Invalid'})
        info = user_view(request)
        self.assertIsInstance(info, HTTPNotFound)


if __name__ == '__main__':
    unittest.main()
