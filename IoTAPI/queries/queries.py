insert_product_query = '''INSERT INTO content(name, expiration_date, warned) VALUES (%s, %s, %s);'''
remove_product_query = '''DELETE FROM content WHERE name = %s AND expiration_date = %s;'''
get_all_products_query = '''SELECT * FROM content;'''