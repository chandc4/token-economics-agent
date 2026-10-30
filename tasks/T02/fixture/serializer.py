import json
from models import User

def serialize_user(user: User) -> str:
    return json.dumps({"name": user.name, "age": user.age})

def deserialize_user(json_str: str) -> User:
    data = json.loads(json_str)
    return User(name=data["name"], age=data["age"])
