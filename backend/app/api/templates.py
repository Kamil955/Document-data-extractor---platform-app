import uuid
from collections.abc import Sequence

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from app.api.deps import SessionDep
from app.models import FieldType, Template, TemplateField
from app.schemas import TemplateCreate, TemplateOut

router = APIRouter(prefix="/templates", tags=["templates"])


@router.post("", status_code=201, response_model=TemplateOut)
async def create_template(body: TemplateCreate, session: SessionDep) -> Template:
    template = Template(
        name=body.name,
        description=body.description,
        # position keeps the order the client sent: the order of fields in a card matters.
        fields=[
            TemplateField(
                key=f.key,
                label=f.label,
                description=f.description,
                field_type=FieldType(f.type),
                position=position,
            )
            for position, f in enumerate(body.fields)
        ],
    )
    session.add(template)
    await session.commit()
    return template


@router.get("", response_model=list[TemplateOut])
async def list_templates(session: SessionDep) -> Sequence[Template]:
    result = await session.execute(select(Template).order_by(Template.created_at.desc()))
    return result.scalars().all()


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(template_id: uuid.UUID, session: SessionDep) -> Template:
    template = await session.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="template not found")
    return template


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: uuid.UUID, session: SessionDep) -> Response:
    template = await session.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="template not found")
    await session.delete(template)  # fields go with it (ON DELETE CASCADE)
    await session.commit()
    return Response(status_code=204)
