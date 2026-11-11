"""Datar una estampa por sus sellos de censura: lo que dice la tabla, como código y no como memoria.

  python censor.py "aratame" "丑" 2 --forma combinado      → [1865]
  python censor.py "kiwame"                               → [1790, 1842]

Fuentes: Self & Hirose, Japanese Art Signatures (1987); las páginas del MIT y de Viewing Japanese
Prints sobre sellos de censor; la misma tabla que lleva el prompt. Las fechas de cada nanushi, solo o
en pareja, son las de Richard Illing, The Art of Japanese Prints (1980), tal como las publica J. N.
Chiappa en http://mercury.lcs.mit.edu/~jnc/prints/nanushi.html (leída el 11/11/2026).
"""
from __future__ import annotations

import json
import sys

ANIMALES = {  # carácter y nombres aceptados → posición en el ciclo
    "子": 0, "rata": 0, "丑": 1, "buey": 1, "寅": 2, "tigre": 2, "卯": 3, "liebre": 3, "conejo": 3,
    "辰": 4, "dragon": 4, "dragón": 4, "巳": 5, "serpiente": 5, "午": 6, "caballo": 6, "未": 7, "cabra": 7, "oveja": 7,
    "申": 8, "mono": 8, "酉": 9, "gallo": 9, "戌": 10, "perro": 10, "亥": 11, "jabali": 11, "jabalí": 11,
}
ANO_RATA = 1852  # 1852 fue año de la Rata; el ciclo es de 12

# tipo de censura → años en que se usó (desde, hasta)
PERIODOS = {
    "kiwame": (1790, 1842),            # 極 solo
    "un_censor": (1842, 1846),         # un nanushi con nombre
    "dos_censores": (1847, 1852),      # dos nanushi
    "dos_censores_fecha": (1852, 1853),
    "aratame_separado": (1853, 1857),  # 改 y la fecha en sellos distintos
    "fecha_sola": (1858, 1858),        # óvalo con animal y mes, sin aratame
    "combinado": (1859, 1871),         # 改 + animal + mes en un sello redondo
    "nengo": (1872, 1876),             # fecha en era; la censura termina en 1876
}
CENSORES = {  # los nanushi más frecuentes, con los años en que firmaron (aproximados, de las listas de referencia)
    "村": ("Mura", 1842, 1853), "浜": ("Hama", 1842, 1853), "福": ("Fuku", 1847, 1852), "衣笠": ("Kinugasa", 1847, 1853),
    "渡辺": ("Watanabe", 1847, 1853), "米良": ("Mera", 1847, 1853), "村松": ("Muramatsu", 1847, 1853), "吉村": ("Yoshimura", 1847, 1852),
    "馬込": ("Magome", 1847, 1853), "高野": ("Takano", 1847, 1852), "田中": ("Tanaka", 1842, 1846), "衣": ("Kinugasa", 1847, 1853),
}

# Quién es cada lectura (los sellos llevan uno o dos caracteres del apellido; 浜 y 濱, 渡辺 y 渡邊 son el mismo).
PERSONA = {
    "高": "Takano", "高野": "Takano", "竹": "Takeguchi", "竹口": "Takeguchi", "村": "Murata", "村田": "Murata",
    "普": "Fukatsu", "普勝": "Fukatsu", "田中": "Tanaka", "渡": "Watanabe Jiemon", "村松": "Muramatsu",
    "浜": "Hama", "濱": "Hama", "吉村": "Yoshimura", "衣笠": "Kinugasa", "衣": "Kinugasa", "馬込": "Magome",
    "渡辺": "Watanabe", "渡邊": "Watanabe", "米良": "Mera", "福": "Fuku", "福島": "Fuku",
}
# Un sello solo (1842-1846): la lectura fija los años. 村 es 1843-1845 y 村田, el mismo censor, 1846.
SOLO = {
    "高": (1842, 1842), "高野": (1842, 1842), "竹": (1842, 1842), "竹口": (1842, 1842), "村": (1843, 1845),
    "普": (1843, 1845), "普勝": (1843, 1845), "田中": (1843, 1845), "渡": (1843, 1845), "村田": (1846, 1846),
    "村松": (1843, 1846), "浜": (1843, 1846), "濱": (1843, 1846), "吉村": (1843, 1846), "衣笠": (1845, 1846),
    "衣": (1845, 1846),
}
# Dos sellos juntos (1847-1853): la pareja fija los años.
PAREJA = {
    frozenset(("Murata", "Kinugasa")): (1851, 1853), frozenset(("Murata", "Mera")): (1847, 1850),
    frozenset(("Muramatsu", "Yoshimura")): (1847, 1848), frozenset(("Muramatsu", "Fuku")): (1849, 1853),
    frozenset(("Hama", "Kinugasa")): (1847, 1848), frozenset(("Hama", "Magome")): (1849, 1853),
    frozenset(("Yoshimura", "Kinugasa")): (1849, 1849), frozenset(("Kinugasa", "Watanabe")): (1849, 1850),
    frozenset(("Watanabe", "Mera")): (1851, 1853),
}
CENSURA_DESDE, CENSURA_HASTA = 1790, 1875  # los años en que una estampa de venta pública llevaba sello


def sello_esperado(desde: int | None, hasta: int | None) -> bool:
    """¿Una estampa de venta pública de esos años debería llevar sello de censura o de fecha? Sin años,
    no se sabe y se contesta que no: quien pregunta decide con lo demás."""
    if not isinstance(desde, int) and not isinstance(hasta, int):
        return False
    d = desde if isinstance(desde, int) else hasta
    h = hasta if isinstance(hasta, int) else desde
    return d <= CENSURA_HASTA and h >= CENSURA_DESDE


def anos_del_animal(animal: str, desde: int, hasta: int) -> list[int]:
    pos = ANIMALES.get(animal.strip().lower() if not animal.strip() in ANIMALES else animal.strip())
    if pos is None:
        return []
    return [a for a in range(desde, hasta + 1) if (a - ANO_RATA) % 12 == pos]


def datar(tipo: str, animal: str | None = None, mes: int | None = None, censores: list[str] | None = None) -> dict:
    """Los años posibles según el tipo de sello, el animal del zodiaco y, si los hay, los censores nominativos."""
    tipo = tipo.strip().lower().replace(" ", "_")
    if tipo not in PERIODOS:
        return {"error": f"tipo desconocido: {tipo}. Son: {', '.join(PERIODOS)}"}
    desde, hasta = PERIODOS[tipo]
    anos = list(range(desde, hasta + 1))
    if animal:
        anos = anos_del_animal(animal, desde, hasta)
        if not anos:
            return {"error": f"animal desconocido: {animal}"}
    for c in censores or []:
        if c in CENSORES:
            _, d, h = CENSORES[c]
            anos = [a for a in anos if d <= a <= h]
    nota = ""
    leidos = [str(c).strip() for c in censores or [] if str(c).strip() in PERSONA]
    quienes = {PERSONA[c] for c in leidos}
    afinado = None
    if tipo in ("dos_censores", "dos_censores_fecha") and len(quienes) == 2 and frozenset(quienes) in PAREJA:
        afinado = PAREJA[frozenset(quienes)]
        nota = f"pareja {' + '.join(sorted(quienes))}: {afinado[0]}-{afinado[1]} (Illing 1980)"
    elif tipo == "un_censor" and len(leidos) == 1 and leidos[0] in SOLO:
        afinado = SOLO[leidos[0]]
        nota = f"sello solo de {PERSONA[leidos[0]]}: {afinado[0]}-{afinado[1]} (Illing 1980)"
    if afinado:
        dentro = [a for a in anos if afinado[0] <= a <= afinado[1]]
        if dentro:  # si la pareja no cabe en el periodo del tipo de sello, manda el tipo y se dice
            anos = dentro
        else:
            nota += "; no cuadra con el tipo de sello: revisa la lectura"
    if tipo == "combinado" and animal and anos == [a for a in range(1859, 1872) if (a - ANO_RATA) % 12 == ANIMALES.get(animal, -1)]:
        nota = "sello redondo combinado: el animal fija el año dentro de 1859-1871"
    if mes and not 1 <= int(mes) <= 12:
        return {"error": "el mes va de 1 a 12 (閏 es intercalar: añádelo en la nota)"}
    return {"tipo": tipo, "anos": anos, "mes": mes, "censores": [CENSORES[c][0] for c in censores or [] if c in CENSORES],
            "nota": nota or f"periodo del sello {desde}-{hasta}"}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("tipo")
    p.add_argument("animal", nargs="?")
    p.add_argument("mes", nargs="?", type=int)
    p.add_argument("--censores", nargs="*")
    a = p.parse_args()
    print(json.dumps(datar(a.tipo, a.animal, a.mes, a.censores), ensure_ascii=False))
