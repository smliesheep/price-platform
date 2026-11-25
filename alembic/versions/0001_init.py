"""初始 schema（对应设计文档 §2.2）。

生成方式：手写，字段与 src/price_platform/models/entities.py 保持一致。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("adapter", sa.Text(), nullable=False),
        sa.Column("rate_limit_per_min", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("proxy_group", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_id", sa.BigInteger(), sa.ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("category", sa.Text()),
        sa.Column("target_price", sa.Numeric(12, 2)),
        sa.Column("selector_version", sa.Text(), nullable=False, server_default="v1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("current_price", sa.Numeric(12, 2)),
        sa.Column("last_collected_at", sa.DateTime(timezone=True)),
        sa.Column("last_status", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("source_id", "external_id", name="uq_products_source_external"),
    )
    op.create_index("idx_products_source", "products", ["source_id"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "product_id",
            sa.BigInteger(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("schedule_type", sa.Text(), nullable=False, server_default="interval"),
        sa.Column("interval_sec", sa.Integer(), nullable=False, server_default="1800"),
        sa.Column("cron_expr", sa.Text()),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="5"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("max_retry", sa.SmallInteger(), nullable=False, server_default="3"),
        sa.Column("timeout_sec", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "(schedule_type = 'interval') OR (schedule_type = 'cron' AND cron_expr IS NOT NULL)",
            name="ck_task_schedule",
        ),
    )
    op.create_index("idx_tasks_due", "tasks", ["next_run_at"], postgresql_where=sa.text("status = 'active'"))

    op.create_table(
        "task_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("worker_id", sa.Text()),
        sa.Column("trace_id", sa.Text()),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("http_status", sa.Integer()),
        sa.Column("error_type", sa.Text()),
        sa.Column("error_msg", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("task_id", "slot_at", "attempt", name="uq_task_runs_slot_attempt"),
        sa.CheckConstraint(
            "status IN ('queued','running','success','failed','timeout','canceled','retry_wait')",
            name="ck_task_runs_status",
        ),
    )
    op.create_index("idx_runs_status_time", "task_runs", ["status", "queued_at"])
    op.create_index("idx_runs_product", "task_runs", ["product_id", "started_at"])
    op.create_index("idx_runs_worker", "task_runs", ["worker_id", "started_at"])
    op.create_index(
        "idx_runs_running", "task_runs", ["started_at"], postgresql_where=sa.text("status = 'running'")
    )
    op.create_index(
        "idx_runs_undispatched",
        "task_runs",
        ["queued_at"],
        postgresql_where=sa.text("status = 'queued' AND dispatched_at IS NULL"),
    )

    op.create_table(
        "price_records",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.BigInteger(), sa.ForeignKey("task_runs.id", ondelete="SET NULL")),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default="CNY"),
        sa.Column("in_stock", sa.Boolean()),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("product_id", "collected_at", name="uq_price_product_collected"),
        sa.CheckConstraint("price >= 0", name="ck_price_non_negative"),
    )
    op.create_index("idx_price_product_time", "price_records", ["product_id", "collected_at"])
    op.create_index("idx_price_time", "price_records", ["collected_at"])

    op.create_table(
        "workers",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("node", sa.Text()),
        sa.Column("version", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("inflight", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("idx_workers_heartbeat", "workers", ["last_heartbeat"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.id", ondelete="CASCADE")),
        sa.Column("rule", sa.Text(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False, server_default="warn"),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("level IN ('info','warn','crit')", name="ck_alerts_level"),
    )
    op.create_index("idx_alerts_time", "alerts", ["triggered_at"])


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("workers")
    op.drop_table("price_records")
    op.drop_table("task_runs")
    op.drop_table("tasks")
    op.drop_table("products")
    op.drop_table("sources")
