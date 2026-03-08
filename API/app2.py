conn = conectar()
c = conn.cursor()

c.execute("""
ALTER TABLE users
ALTER COLUMN saldo TYPE NUMERIC(10,2)
""")

conn.commit()
conn.close()
