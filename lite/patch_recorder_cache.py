# HA Lite (generic): recorder SQLite page cache 16 MB -> 1 MB. Writes are unchanged; long history queries are slower.
# Cache do SQLite do recorder: o HA fixa 16 MB (PRAGMA cache_size = -16384); o padrao do proprio SQLite e ~2 MB.
# Quem nao usa historico nao precisa: gravacao segue normal, so consultas longas ficam mais lentas. 1 MB aqui.
import sys
p = "/usr/src/homeassistant/homeassistant/components/recorder/util.py"
s = open(p, encoding="utf-8").read()
a = 'execute_on_connection(dbapi_connection, "PRAGMA cache_size = -16384")'
if s.count(a) != 1:
    sys.exit("rc_patch: linha do cache_size nao encontrada")
open(p, "w", encoding="utf-8").write(s.replace(a, a.replace("-16384", "-1024")))
print("rc_patch aplicado (cache do SQLite 16 MB -> 1 MB)")
