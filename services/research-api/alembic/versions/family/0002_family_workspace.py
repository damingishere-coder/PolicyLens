"""Keep existing IDs and payments while allowing incomplete family policy records."""

import sqlalchemy as sa

from alembic import op
from policylens_api.models import family_metadata

revision = "family_0002"
down_revision = "family_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # The original initial revision uses current metadata on a fresh database.
    for table, columns in {
        "persons": [
            sa.Column("profile_encrypted", sa.Text()),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        ],
        "policies": [
            sa.Column("details_encrypted", sa.Text()),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        ],
        "policy_premium_records": [
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1")
        ],
    }.items():
        existing = {c["name"] for c in sa.inspect(bind).get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)
    policy_columns = {c["name"]: c for c in sa.inspect(bind).get_columns("policies")}
    constraints = {c["name"] for c in sa.inspect(bind).get_unique_constraints("policies")}
    if (
        not policy_columns["product_version_id"]["nullable"]
        or not policy_columns["person_id"]["nullable"]
        or "uq_person_product_version" in constraints
    ):
        with op.batch_alter_table("policies", recreate="always") as batch:
            batch.alter_column("person_id", existing_type=sa.String(40), nullable=True)
            batch.alter_column("product_version_id", existing_type=sa.String(40), nullable=True)
            if "uq_person_product_version" in constraints:
                batch.drop_constraint("uq_person_product_version", type_="unique")
    family_metadata.create_all(bind=bind)


def downgrade() -> None:
    raise RuntimeError(
        "Restore the verified pre-migration backup with the previous application version; automatic downgrade would discard family records."
    )
