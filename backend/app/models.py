from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Atividade(Base):
    """Uma atividade do planejamento semanal de lavra."""

    __tablename__ = "atividades"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str | None] = mapped_column(String(50), index=True)
    descricao: Mapped[str] = mapped_column(String(255))
    tipo: Mapped[str | None] = mapped_column(String(80), index=True)          # Perfuração, Desmonte, Carregamento...
    frente: Mapped[str | None] = mapped_column(String(80), index=True)        # frente de lavra / cava / banco
    equipamento: Mapped[str | None] = mapped_column(String(80))
    responsavel: Mapped[str | None] = mapped_column(String(80))
    unidade: Mapped[str] = mapped_column(String(20), default="t")
    qtd_planejada: Mapped[float] = mapped_column(Float, default=0.0)
    inicio_planejado: Mapped[date] = mapped_column(Date, index=True)
    fim_planejado: Mapped[date] = mapped_column(Date, index=True)
    inicio_real: Mapped[date | None] = mapped_column(Date)
    fim_real: Mapped[date | None] = mapped_column(Date)
    # Usado apenas quando a atividade não tem quantidade (qtd_planejada = 0), ex.: manutenção de acesso.
    progresso_manual: Mapped[float | None] = mapped_column(Float)
    observacoes: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    apontamentos: Mapped[list["Apontamento"]] = relationship(
        back_populates="atividade", cascade="all, delete-orphan", order_by="Apontamento.data"
    )

    @property
    def qtd_realizada(self) -> float:
        return round(sum(a.quantidade for a in self.apontamentos), 4)

    @property
    def ultimo_apontamento(self) -> date | None:
        return max((a.data for a in self.apontamentos if a.quantidade), default=None)


class Apontamento(Base):
    """Registro de produção realizada (andamento) de uma atividade em um dia."""

    __tablename__ = "apontamentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    atividade_id: Mapped[int] = mapped_column(ForeignKey("atividades.id", ondelete="CASCADE"), index=True)
    data: Mapped[date] = mapped_column(Date, index=True)
    quantidade: Mapped[float] = mapped_column(Float)
    observacao: Mapped[str | None] = mapped_column(String(255))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    atividade: Mapped[Atividade] = relationship(back_populates="apontamentos")


class Equipamento(Base):
    """Equipamento da frota (escavadeira, caminhão, perfuratriz...)."""

    __tablename__ = "equipamentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(50), unique=True, index=True)   # ex.: ES-01, CM-07
    descricao: Mapped[str | None] = mapped_column(String(120))                 # modelo / fabricante
    categoria: Mapped[str | None] = mapped_column(String(80), index=True)      # Escavadeira, Caminhão...
    frente: Mapped[str | None] = mapped_column(String(80))                     # alocação padrão
    meta_df: Mapped[float] = mapped_column(Float, default=0.85)                # meta de disponibilidade física
    intervalo_preventiva_h: Mapped[float | None] = mapped_column(Float)        # ex.: 250 h entre preventivas
    horimetro_ultima_preventiva: Mapped[float | None] = mapped_column(Float)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    observacoes: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    paradas: Mapped[list["Parada"]] = relationship(
        back_populates="equipamento", cascade="all, delete-orphan", order_by="Parada.inicio"
    )
    registros_horas: Mapped[list["RegistroHoras"]] = relationship(
        back_populates="equipamento", cascade="all, delete-orphan", order_by="RegistroHoras.data"
    )

    @property
    def horimetro_atual(self) -> float | None:
        leituras = [r.horimetro for r in self.registros_horas if r.horimetro is not None]
        leituras += [p.horimetro for p in self.paradas if p.horimetro is not None]
        return max(leituras, default=None)


class Parada(Base):
    """Período em que o equipamento ficou (ou ficará) parado.

    corretiva / preventiva = manutenção (reduz a disponibilidade física);
    operacional = parado por outro motivo (falta de operador, clima, sem frente) — reduz só a utilização.
    ``fim`` nulo = parada em aberto (equipamento ainda parado).
    """

    __tablename__ = "paradas"

    id: Mapped[int] = mapped_column(primary_key=True)
    equipamento_id: Mapped[int] = mapped_column(ForeignKey("equipamentos.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    inicio: Mapped[datetime] = mapped_column(DateTime, index=True)
    fim: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    motivo: Mapped[str | None] = mapped_column(String(255))
    horimetro: Mapped[float | None] = mapped_column(Float)                     # leitura no início da parada
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    equipamento: Mapped[Equipamento] = relationship(back_populates="paradas")


class RegistroHoras(Base):
    """Horas trabalhadas do equipamento em um dia (e leitura de horímetro, se houver)."""

    __tablename__ = "registros_horas"

    id: Mapped[int] = mapped_column(primary_key=True)
    equipamento_id: Mapped[int] = mapped_column(ForeignKey("equipamentos.id", ondelete="CASCADE"), index=True)
    data: Mapped[date] = mapped_column(Date, index=True)
    horas_trabalhadas: Mapped[float] = mapped_column(Float, default=0.0)
    horimetro: Mapped[float | None] = mapped_column(Float)
    observacao: Mapped[str | None] = mapped_column(String(255))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    equipamento: Mapped[Equipamento] = relationship(back_populates="registros_horas")
