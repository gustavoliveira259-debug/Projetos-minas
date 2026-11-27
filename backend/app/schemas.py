from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AtividadeBase(BaseModel):
    codigo: str | None = Field(None, max_length=50)
    descricao: str = Field(..., min_length=1, max_length=255)
    tipo: str | None = Field(None, max_length=80)
    frente: str | None = Field(None, max_length=80)
    equipamento: str | None = Field(None, max_length=80)
    responsavel: str | None = Field(None, max_length=80)
    unidade: str = Field("t", max_length=20)
    qtd_planejada: float = Field(0, ge=0)
    inicio_planejado: date
    fim_planejado: date
    inicio_real: date | None = None
    fim_real: date | None = None
    progresso_manual: float | None = Field(None, ge=0, le=100)
    observacoes: str | None = None


class AtividadeCreate(AtividadeBase):
    predecessoras: list[int] = Field(default_factory=list, description="IDs das atividades das quais esta depende")

    @model_validator(mode="after")
    def _datas(self):
        validar_datas(self.model_dump())
        return self


def validar_datas(d: dict):
    ini, fim = d.get("inicio_planejado"), d.get("fim_planejado")
    if ini and fim and fim < ini:
        raise ValueError("O fim planejado não pode ser anterior ao início planejado.")
    ir, fr = d.get("inicio_real"), d.get("fim_real")
    if ir and fr and fr < ir:
        raise ValueError("O fim real não pode ser anterior ao início real.")


class AtividadeUpdate(BaseModel):
    """Atualização parcial (PATCH): só os campos enviados são alterados."""

    codigo: str | None = Field(None, max_length=50)
    descricao: str | None = Field(None, min_length=1, max_length=255)
    tipo: str | None = None
    frente: str | None = None
    equipamento: str | None = None
    responsavel: str | None = None
    unidade: str | None = Field(None, max_length=20)
    qtd_planejada: float | None = Field(None, ge=0)
    inicio_planejado: date | None = None
    fim_planejado: date | None = None
    inicio_real: date | None = None
    fim_real: date | None = None
    progresso_manual: float | None = Field(None, ge=0, le=100)
    observacoes: str | None = None
    predecessoras: list[int] | None = None


class SituacaoOut(BaseModel):
    status: str
    rotulo: str
    progresso_real: float
    progresso_esperado: float
    desvio: float
    qtd_realizada: float
    qtd_esperada: float
    saldo: float
    projecao: float
    impacto_meta: float
    dias_atraso: int
    data_conclusao: date | None
    concluida_com_atraso: bool


class AtividadeRef(BaseModel):
    """Referência curta a outra atividade (dependências)."""

    id: int
    codigo: str | None
    descricao: str
    inicio_planejado: date
    fim_planejado: date


class AtividadeOut(AtividadeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    qtd_realizada: float
    criado_em: datetime | None = None
    atualizado_em: datetime | None = None
    situacao: SituacaoOut
    predecessoras: list[AtividadeRef] = []
    sucessoras: list[AtividadeRef] = []
    # Preenchido só na resposta de uma alteração: dependentes empurradas por ela.
    empurradas: list[AtividadeRef] = []


class ApontamentoCreate(BaseModel):
    data: date
    quantidade: float = Field(..., ge=0)
    observacao: str | None = Field(None, max_length=255)
    concluir: bool = False  # marca a atividade como concluída nesta data


class ApontamentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    atividade_id: int
    data: date
    quantidade: float
    observacao: str | None
    criado_em: datetime | None = None


# ---------- Equipamentos ----------

TipoParada = Literal["corretiva", "preventiva", "operacional"]


class EquipamentoBase(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=50)
    descricao: str | None = Field(None, max_length=120)
    categoria: str | None = Field(None, max_length=80)
    frente: str | None = Field(None, max_length=80)
    meta_df: float = Field(0.85, ge=0, le=1)
    intervalo_preventiva_h: float | None = Field(None, gt=0)
    horimetro_ultima_preventiva: float | None = Field(None, ge=0)
    ativo: bool = True
    observacoes: str | None = None


class EquipamentoCreate(EquipamentoBase):
    pass


class EquipamentoUpdate(BaseModel):
    codigo: str | None = Field(None, min_length=1, max_length=50)
    descricao: str | None = Field(None, max_length=120)
    categoria: str | None = Field(None, max_length=80)
    frente: str | None = Field(None, max_length=80)
    meta_df: float | None = Field(None, ge=0, le=1)
    intervalo_preventiva_h: float | None = Field(None, gt=0)
    horimetro_ultima_preventiva: float | None = Field(None, ge=0)
    ativo: bool | None = None
    observacoes: str | None = None


class EquipamentoOut(EquipamentoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    horimetro_atual: float | None = None


class ParadaCreate(BaseModel):
    tipo: TipoParada
    inicio: datetime
    fim: datetime | None = None
    motivo: str | None = Field(None, max_length=255)
    horimetro: float | None = Field(None, ge=0)

    @model_validator(mode="after")
    def _datas(self):
        if self.fim and self.fim <= self.inicio:
            raise ValueError("O fim da parada deve ser posterior ao início.")
        return self


class ParadaUpdate(BaseModel):
    tipo: TipoParada | None = None
    inicio: datetime | None = None
    fim: datetime | None = None
    motivo: str | None = Field(None, max_length=255)
    horimetro: float | None = Field(None, ge=0)


class ParadaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    equipamento_id: int
    tipo: str
    inicio: datetime
    fim: datetime | None
    motivo: str | None
    horimetro: float | None


class RegistroHorasCreate(BaseModel):
    data: date
    horas_trabalhadas: float = Field(..., ge=0, le=24)
    horimetro: float | None = Field(None, ge=0)
    observacao: str | None = Field(None, max_length=255)


class RegistroHorasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    equipamento_id: int
    data: date
    horas_trabalhadas: float
    horimetro: float | None
    observacao: str | None
