class User:
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age

    def to_dict(self):
        return {"name": self.name, "age": self.age}
