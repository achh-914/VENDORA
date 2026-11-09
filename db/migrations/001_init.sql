-- Vendora: initial schema (PostgreSQL 16 + pgvector)
-- Principles: every conclusion has evidence, every step is logged, a person approves.

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------- enums ----------
CREATE TYPE case_status AS ENUM (
  'processing', 'cleared', 'awaiting_approval',
  'approved', 'rejected', 'changes_requested', 'failed'
);
CREATE TYPE doc_type AS ENUM ('invoice', 'purchase_order', 'contract', 'correspondence');
CREATE TYPE discrepancy_type AS ENUM (
  'PRICE-MISMATCH', 'UNAGREED-FEE', 'QTY-VARIANCE', 'DUPLICATE-LINE', 'TERMS-CONFLICT'
);
CREATE TYPE discrepancy_status AS ENUM ('open', 'explained', 'dismissed');
CREATE TYPE agent_name AS ENUM ('extraction', 'matching', 'investigation', 'supervisor');
CREATE TYPE action_type AS ENUM ('HOLD_INVOICE', 'DRAFT_SUPPLIER_MESSAGE', 'ESCALATE');
CREATE TYPE action_status AS ENUM ('proposed', 'approved', 'rejected', 'executed_simulated');
CREATE TYPE decision AS ENUM ('approved', 'rejected', 'changes_requested');

-- ---------- cases and documents ----------
CREATE TABLE cases (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  supplier_name text,
  status        case_status NOT NULL DEFAULT 'processing',
  summary       text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE documents (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id     uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  doc_type    doc_type NOT NULL,
  filename    text NOT NULL,
  storage_key text NOT NULL,            -- path in Object Storage
  sha256      char(64) NOT NULL,
  page_count  int,
  uploaded_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (case_id, sha256)
);
CREATE INDEX documents_case_idx ON documents(case_id);

-- ---------- extraction output ----------
CREATE TABLE extracted_fields (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id   uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  field_name    text NOT NULL,          -- e.g. total, currency, payment_terms
  value_text    text,
  value_numeric numeric(14,2),
  page          int,
  confidence    real CHECK (confidence BETWEEN 0 AND 1),
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX extracted_fields_doc_idx ON extracted_fields(document_id, field_name);

CREATE TABLE line_items (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  line_no     int NOT NULL,
  description text NOT NULL,
  quantity    numeric(14,3),
  unit_price  numeric(14,2),
  amount      numeric(14,2),
  page        int,
  UNIQUE (document_id, line_no)
);

CREATE TABLE clauses (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  clause_ref  text,                     -- e.g. "4.2"
  page        int,
  body        text NOT NULL,
  embedding   vector(1024)              -- match the dimension of your embedding model
);
CREATE INDEX clauses_doc_idx ON clauses(document_id);
CREATE INDEX clauses_embedding_idx ON clauses USING hnsw (embedding vector_cosine_ops);

-- ---------- findings ----------
CREATE TABLE discrepancies (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id      uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  type         discrepancy_type NOT NULL,
  amount_delta numeric(14,2),
  description  text NOT NULL,
  root_cause   text,
  status       discrepancy_status NOT NULL DEFAULT 'open',
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX discrepancies_case_idx ON discrepancies(case_id);

-- Every conclusion points to a document, page and clause or line item.
CREATE TABLE evidence (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  discrepancy_id uuid NOT NULL REFERENCES discrepancies(id) ON DELETE CASCADE,
  document_id    uuid NOT NULL REFERENCES documents(id),
  page           int,
  clause_id      uuid REFERENCES clauses(id),
  line_item_id   uuid REFERENCES line_items(id),
  quote          text NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX evidence_discrepancy_idx ON evidence(discrepancy_id);

-- ---------- actions and human approval ----------
CREATE TABLE proposed_actions (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id    uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  type       action_type NOT NULL,
  payload    jsonb NOT NULL DEFAULT '{}',
  status     action_status NOT NULL DEFAULT 'proposed',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX proposed_actions_case_idx ON proposed_actions(case_id);

CREATE TABLE approvals (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id            uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  proposed_action_id uuid REFERENCES proposed_actions(id),
  decision           decision NOT NULL,
  decided_by         text NOT NULL,     -- a person, never an agent
  comment            text,
  decided_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX approvals_case_idx ON approvals(case_id);

-- ---------- agent runs and audit ----------
CREATE TABLE agent_runs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id       uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  agent         agent_name NOT NULL,
  model         text NOT NULL,
  input_tokens  int,
  output_tokens int,
  cost_usd      numeric(10,4),
  status        text NOT NULL DEFAULT 'running',
  error         text,
  started_at    timestamptz NOT NULL DEFAULT now(),
  finished_at   timestamptz
);
CREATE INDEX agent_runs_case_idx ON agent_runs(case_id);

CREATE TABLE audit_log (
  id         bigserial PRIMARY KEY,
  case_id    uuid REFERENCES cases(id),
  actor_type text NOT NULL CHECK (actor_type IN ('agent', 'human', 'system')),
  actor      text NOT NULL,
  event_type text NOT NULL,
  payload    jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_case_idx ON audit_log(case_id, created_at);

-- The audit trail is append-only.
CREATE FUNCTION audit_log_immutable() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_no_change
  BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();
CREATE TRIGGER audit_log_no_truncate
  BEFORE TRUNCATE ON audit_log
  FOR EACH STATEMENT EXECUTE FUNCTION audit_log_immutable();

-- ---------- evaluation ----------
CREATE TABLE eval_runs (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  git_sha    text,
  model      text,
  notes      text,
  started_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE eval_results (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id               uuid NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
  eval_case_key        text NOT NULL,   -- matches a case file in eval/
  expected_type        discrepancy_type,
  detected_type        discrepancy_type,
  type_correct         boolean,
  root_cause_correct   boolean,
  evidence_correct     boolean,
  cost_usd             numeric(10,4)
);
CREATE INDEX eval_results_run_idx ON eval_results(run_id);

-- ---------- housekeeping ----------
CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER cases_updated_at
  BEFORE UPDATE ON cases
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
