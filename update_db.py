import sqlite3
conn = sqlite3.connect('sigrama.db')
c = conn.cursor()
c.execute("UPDATE avances SET area = 'Empaque' WHERE area = 'Entregado'")
c.execute("UPDATE rechazos SET area = 'Empaque' WHERE area = 'Entregado'")
conn.commit()
conn.close()
