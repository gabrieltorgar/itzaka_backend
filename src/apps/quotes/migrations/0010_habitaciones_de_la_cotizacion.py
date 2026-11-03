"""Las habitaciones de la cotización (iteracion-31, US-10 · US-11).

El apartado «Habitaciones» de la cotización, con su orden, y su aislamiento por
empresa en la base desde que nace (SEC-01, como 0009): se ve y se escribe sólo
con el contexto de la empresa dueña de su cotización. Sin datos que copiar: las
habitaciones que ya usan las partidas las lee la API de ellas mismas.
"""

import uuid

import django.db.models.deletion
import django.db.models.functions.text
from django.db import migrations, models

from common.rls import IsolateCompanies

POLICIES = {
    "quotes_quote_room": (
        "EXISTS (SELECT 1 FROM quotes_quote q "
        "WHERE q.id = quotes_quote_room.quote_id AND q.owner_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    ),
}


class Migration(migrations.Migration):
    dependencies = [
        ("quotes", "0009_aislamiento_por_empresa"),
    ]

    operations = [
        migrations.CreateModel(
            name="QuoteRoom",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="creado en"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="actualizado en"),
                ),
                ("name", models.CharField(max_length=150, verbose_name="habitación")),
                (
                    "position",
                    models.PositiveSmallIntegerField(default=0, verbose_name="orden"),
                ),
                (
                    "quote",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rooms",
                        to="quotes.quote",
                        verbose_name="cotización",
                    ),
                ),
            ],
            options={
                "verbose_name": "habitación de la cotización",
                "verbose_name_plural": "habitaciones de la cotización",
                "db_table": "quotes_quote_room",
                "ordering": ["position", "created_at"],
                "constraints": [
                    models.UniqueConstraint(
                        django.db.models.functions.text.Lower("name"),
                        models.F("quote"),
                        name="quotes_quote_room_once",
                    )
                ],
            },
        ),
        IsolateCompanies(POLICIES),
    ]
