"""Lógica del Truco argentino (1 contra 1, sin flor) y la inteligencia de la compu."""

import random
from dataclasses import dataclass, field

PALOS = ("espada", "basto", "oro", "copa")
NUMEROS = (1, 2, 3, 4, 5, 6, 7, 10, 11, 12)

VOS, CPU = 0, 1
NOMBRES = ("Vos", "CPU")

NOMBRE_TRUCO = {2: "Truco", 3: "Retruco", 4: "Vale cuatro"}
NOMBRE_ENVIDO = {"envido": "Envido", "real": "Real envido", "falta": "Falta envido"}
VALOR_ENVIDO = {"envido": 2, "real": 3}


@dataclass(frozen=True)
class Carta:
    numero: int
    palo: str

    @property
    def poder(self):
        """Jerarquía del truco: 14 = ancho de espada ... 1 = los cuatros."""
        n, p = self.numero, self.palo
        if (n, p) == (1, "espada"):
            return 14
        if (n, p) == (1, "basto"):
            return 13
        if (n, p) == (7, "espada"):
            return 12
        if (n, p) == (7, "oro"):
            return 11
        return {3: 10, 2: 9, 1: 8, 12: 7, 11: 6, 10: 5, 7: 4, 6: 3, 5: 2, 4: 1}[n]

    @property
    def valor_envido(self):
        return 0 if self.numero >= 10 else self.numero

    def __str__(self):
        return f"{self.numero} de {self.palo}"


MAZO = [Carta(n, p) for p in PALOS for n in NUMEROS]


def puntos_envido(cartas):
    mejor = max(c.valor_envido for c in cartas)
    for palo in PALOS:
        del_palo = sorted((c.valor_envido for c in cartas if c.palo == palo), reverse=True)
        if len(del_palo) >= 2:
            mejor = max(mejor, 20 + del_palo[0] + del_palo[1])
    return mejor


def ganador_mano(resultados, mano):
    """resultados: ganador de cada baza (VOS, CPU o None si fue parda).
    Devuelve quién gana la mano, o None si todavía no está definida."""
    for j in (VOS, CPU):
        if resultados.count(j) >= 2:
            return j
    if len(resultados) >= 2:
        a, b = resultados[0], resultados[1]
        if a is None and b is not None:
            return b
        if a is not None and b is None:
            return a
    if len(resultados) == 3:
        a, b, c = resultados
        if c is not None:
            return c
        return a if a is not None else mano
    return None


@dataclass
class Canto:
    tipo: str          # "truco" o "envido"
    por: int           # quién cantó
    nivel: int = 0     # para truco: 2, 3 o 4


@dataclass
class Mano:
    """Una mano (reparto) del truco."""

    mano: int                      # quién es mano
    puntaje: list                  # referencia al puntaje del partido
    meta: int
    cartas: list = field(default_factory=list)       # cartas en la mano de cada jugador
    jugadas: list = field(default_factory=list)      # por baza: [carta_vos, carta_cpu]
    resultados: list = field(default_factory=list)
    turno: int = 0
    truco: int = 1                 # valor de la mano (aceptado)
    ultimo_truco: int | None = None  # quién hizo el último canto de truco aceptado
    envido_cadena: list = field(default_factory=list)
    envido_hecho: bool = False
    pendientes: list = field(default_factory=list)   # pila de cantos esperando respuesta
    terminada: bool = False
    ganador: int | None = None
    eventos: list = field(default_factory=list)      # (jugador o None, texto)

    @classmethod
    def repartir(cls, mano, puntaje, meta):
        m = cls(mano=mano, puntaje=puntaje, meta=meta, turno=mano)
        mazo = MAZO[:]
        random.shuffle(mazo)
        m.cartas = [mazo[0:3], mazo[3:6]]
        m.envido_original = [puntos_envido(m.cartas[0]), puntos_envido(m.cartas[1])]
        m.jugadas = [[None, None]]
        return m

    # ------------------------------------------------------------------ consultas
    @property
    def baza(self):
        return len(self.jugadas) - 1

    @property
    def pendiente(self):
        return self.pendientes[-1] if self.pendientes else None

    def quien_actua(self):
        """Jugador que tiene que hacer algo ahora."""
        if self.terminada:
            return None
        if self.pendiente:
            return 1 - self.pendiente.por
        return self.turno

    def puede_envido(self, j):
        return (not self.envido_hecho and self.baza == 0 and self.truco == 1
                and self.jugadas[0][j] is None)

    def acciones(self, j):
        """Acciones legales del jugador j en este momento."""
        if self.quien_actua() != j:
            return []
        p = self.pendiente
        acc = []
        if p and p.tipo == "truco":
            acc += ["quiero", "no_quiero"]
            if p.nivel < 4:
                acc.append("truco")
            if p.nivel == 2 and self.puede_envido(j):
                acc += ["envido", "real", "falta"]
        elif p and p.tipo == "envido":
            acc += ["quiero", "no_quiero"]
            c = self.envido_cadena
            if c.count("envido") < 2 and "real" not in c and "falta" not in c:
                acc.append("envido")
            if "real" not in c and "falta" not in c:
                acc.append("real")
            if "falta" not in c:
                acc.append("falta")
        else:
            acc.append("jugar")
            if self.truco < 4 and self.ultimo_truco != j:
                acc.append("truco")
            if self.puede_envido(j):
                acc += ["envido", "real", "falta"]
            acc.append("mazo")
        return acc

    def proximo_truco(self):
        p = self.pendiente
        if p and p.tipo == "truco":
            return p.nivel + 1
        return self.truco + 1

    # ------------------------------------------------------------------ acciones
    def decir(self, j, texto):
        self.eventos.append((j, texto))

    def sumar(self, j, puntos, motivo):
        self.puntaje[j] = min(self.meta, self.puntaje[j] + puntos)
        self.decir(None, f"{NOMBRES[j]} +{puntos} ({motivo})")
        if self.puntaje[j] >= self.meta:
            self.terminar(j)

    def terminar(self, ganador):
        self.terminada = True
        if self.ganador is None:
            self.ganador = ganador

    def hacer(self, j, accion, carta=None):
        if accion not in self.acciones(j):
            return False
        getattr(self, f"_{accion}")(j, carta) if accion == "jugar" else getattr(self, f"_{accion}")(j)
        return True

    def _jugar(self, j, carta):
        self.cartas[j].remove(carta)
        self.jugadas[-1][j] = carta
        actual = self.jugadas[-1]
        if actual[1 - j] is None:
            self.turno = 1 - j
            return
        a, b = actual[VOS].poder, actual[CPU].poder
        gana = VOS if a > b else CPU if b > a else None
        self.resultados.append(gana)
        self.decir(None, f"Baza {len(self.resultados)}: " + (f"gana {NOMBRES[gana]}" if gana is not None else "parda"))
        final = ganador_mano(self.resultados, self.mano)
        if final is not None:
            self.sumar(final, self.truco, NOMBRE_TRUCO.get(self.truco, "mano"))
            self.terminar(final)
            return
        self.jugadas.append([None, None])
        self.turno = gana if gana is not None else self.mano

    def _truco(self, j):
        nivel = self.proximo_truco()
        p = self.pendiente
        if p and p.tipo == "truco":
            # "Quiero retruco": acepta lo anterior y sube.
            self.truco = p.nivel
            self.pendientes.pop()
        self.pendientes.append(Canto("truco", j, nivel))
        self.decir(j, ("¡Quiero " if p else "¡") + NOMBRE_TRUCO[nivel] + "!")

    def _canto_envido(self, j, tipo):
        self.envido_cadena.append(tipo)
        p = self.pendiente
        if p and p.tipo == "envido":
            self.pendientes.pop()
        self.pendientes.append(Canto("envido", j))
        self.decir(j, f"¡{NOMBRE_ENVIDO[tipo]}!")

    def _envido(self, j):
        self._canto_envido(j, "envido")

    def _real(self, j):
        self._canto_envido(j, "real")

    def _falta(self, j):
        self._canto_envido(j, "falta")

    def valor_falta(self):
        return self.meta - max(self.puntaje)

    def _quiero(self, j):
        p = self.pendientes.pop()
        self.decir(j, "¡Quiero!")
        if p.tipo == "truco":
            self.truco = p.nivel
            self.ultimo_truco = p.por
            return
        self.envido_hecho = True
        c = self.envido_cadena
        puntos = self.valor_falta() if "falta" in c else sum(VALOR_ENVIDO[t] for t in c)
        ev = self.envido_original
        primero = self.mano
        self.decir(primero, f"Tengo {ev[primero]}")
        self.decir(1 - primero, f"Tengo {ev[1 - primero]}" if ev[1 - primero] > ev[primero] else "Son buenas")
        gana = VOS if ev[VOS] > ev[CPU] else CPU if ev[CPU] > ev[VOS] else self.mano
        self.sumar(gana, puntos, "envido")

    def _no_quiero(self, j):
        p = self.pendientes.pop()
        self.decir(j, "No quiero")
        if p.tipo == "truco":
            self.sumar(p.por, self.truco, "truco no querido")
            self.terminar(p.por)
            return
        self.envido_hecho = True
        c = self.envido_cadena
        puntos = 1 if len(c) == 1 else sum(VALOR_ENVIDO.get(t, 0) for t in c[:-1])
        self.sumar(p.por, max(1, puntos), "envido no querido")

    def _mazo(self, j):
        self.decir(j, "Me voy al mazo")
        self.sumar(1 - j, self.truco, "se fue al mazo")
        self.terminar(1 - j)


# ====================================================================== la compu
class Compu:
    def __init__(self, simulaciones=300):
        self.sims = simulaciones

    def prob_ganar(self, m: Mano):
        """Monte Carlo: reparte cartas desconocidas al rival y juega el resto de la mano."""
        mias = m.cartas[CPU]
        vistas = set(mias) | {c for baza in m.jugadas for c in baza if c}
        resto = [c for c in MAZO if c not in vistas]
        n_rival = len(m.cartas[VOS])
        ganadas = 0
        for _ in range(self.sims):
            rival = random.sample(resto, n_rival)
            ganadas += self._simular(m, list(mias), rival) == CPU
        return ganadas / self.sims

    def _simular(self, m, mias, rival):
        resultados = list(m.resultados)
        actual = list(m.jugadas[-1])
        turno = m.turno
        manos = {CPU: sorted(mias, key=lambda c: c.poder), VOS: sorted(rival, key=lambda c: c.poder)}
        while True:
            for _ in range(2):
                if actual[turno] is None:
                    otra = actual[1 - turno]
                    cartas = manos[turno]
                    if otra is None:
                        carta = cartas[-1]
                    else:
                        mejores = [c for c in cartas if c.poder > otra.poder]
                        carta = mejores[0] if mejores else cartas[0]
                    cartas.remove(carta)
                    actual[turno] = carta
                    turno = 1 - turno
            a, b = actual[VOS].poder, actual[CPU].poder
            gana = VOS if a > b else CPU if b > a else None
            resultados.append(gana)
            final = ganador_mano(resultados, m.mano)
            if final is not None:
                return final
            actual = [None, None]
            turno = gana if gana is not None else m.mano

    def decidir(self, m: Mano):
        """Devuelve (accion, carta)."""
        acc = m.acciones(CPU)
        p = m.pendiente
        env = m.envido_original[CPU]
        mano_bonus = 1 if m.mano == CPU else 0

        # --- responder envido
        if p and p.tipo == "envido":
            c = m.envido_cadena
            if "falta" in acc and env >= 32:
                return "falta", None
            if "real" in acc and env >= 31 and random.random() < 0.6:
                return "real", None
            necesita = 31 if "falta" in c else 29 if "real" in c else 27
            return ("quiero" if env + mano_bonus >= necesita or random.random() < 0.08 else "no_quiero"), None

        # --- "el envido está primero"
        if "envido" in acc and env >= 27 and (p is None or random.random() < 0.85):
            if env >= 31 and random.random() < 0.4:
                return "real", None
            return "envido", None
        if "envido" in acc and p is None and env < 20 and random.random() < 0.07:
            return "envido", None  # mentira

        prob = self.prob_ganar(m)

        # --- responder truco
        if p and p.tipo == "truco":
            if "truco" in acc and prob > 0.78:
                return "truco", None
            umbral = {2: 0.42, 3: 0.52, 4: 0.6}[p.nivel]
            if prob >= umbral or random.random() < 0.06:
                return "quiero", None
            return "no_quiero", None

        # --- cantar truco
        if "truco" in acc:
            umbral = {2: 0.66, 3: 0.76, 4: 0.85}[m.proximo_truco()]
            if prob >= umbral or (m.truco == 1 and random.random() < 0.06):
                return "truco", None

        if prob < 0.05 and m.truco >= 3 and "mazo" in acc:
            return "mazo", None

        return "jugar", self.elegir_carta(m)

    def elegir_carta(self, m: Mano):
        cartas = sorted(m.cartas[CPU], key=lambda c: c.poder)
        rival = m.jugadas[-1][VOS]
        if rival is not None:
            mejores = [c for c in cartas if c.poder > rival.poder]
            if mejores:
                return mejores[0]
            iguales = [c for c in cartas if c.poder == rival.poder]
            if iguales and m.resultados and m.resultados[0] == CPU:
                return iguales[0]  # parda me alcanza
            return cartas[0]
        # salgo yo
        if m.resultados and m.resultados[-1] != CPU:
            return cartas[-1]  # perdí o empaté la anterior: voy con todo
        if len(cartas) == 3:
            return cartas[1]
        return cartas[0]  # ya gané la anterior: tiro la más baja
