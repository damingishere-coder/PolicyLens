"""Create the research and evidence schema.

Revision ID: research_0001
Revises:
"""

from alembic import op
from policylens_api.models import research_metadata

revision = "research_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    research_metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    research_metadata.drop_all(bind=op.get_bind())
