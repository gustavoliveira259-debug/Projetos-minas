from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text, func
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
