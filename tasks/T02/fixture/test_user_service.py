import unittest
from models import User
from serializer import serialize_user, deserialize_user

class TestUserService(unittest.TestCase):
    def test_user_without_email(self):
        u = User("Alice", 30)
        self.assertIsNone(u.email)
        self.assertEqual(u.to_dict(), {"name": "Alice", "age": 30, "email": None})
        
        s = serialize_user(u)
        u2 = deserialize_user(s)
        self.assertEqual(u2.name, "Alice")
        self.assertEqual(u2.age, 30)
        self.assertIsNone(u2.email)

    def test_user_with_email(self):
        u = User("Bob", 25, email="bob@example.com")
        self.assertEqual(u.email, "bob@example.com")
        self.assertEqual(u.to_dict(), {"name": "Bob", "age": 25, "email": "bob@example.com"})

        s = serialize_user(u)
        u2 = deserialize_user(s)
        self.assertEqual(u2.name, "Bob")
        self.assertEqual(u2.age, 25)
        self.assertEqual(u2.email, "bob@example.com")

if __name__ == "__main__":
    unittest.main()
