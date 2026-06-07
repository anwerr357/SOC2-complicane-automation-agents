def create_user(db, name):
    db.execute("INSERT INTO users (name) VALUES (?)", (name,))
    return name
