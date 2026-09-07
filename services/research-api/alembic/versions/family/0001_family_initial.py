"""Create the encrypted family workspace schema.

Revision ID: family_0001
Revises:
"""

from alembic import op
from policylens_api.models import family_metadata

revision = "family_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    family_metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    family_metadata.drop_all(bind=op.get_bind())
