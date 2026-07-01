-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Organizations
CREATE TABLE organizations (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Organization members with role-based access
CREATE TABLE organization_members (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      UUID REFERENCES organizations(id) ON DELETE CASCADE,
  user_id     UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  role        TEXT CHECK (role IN ('owner', 'admin', 'engineer', 'viewer')) NOT NULL,
  invited_by  UUID REFERENCES auth.users(id),
  joined_at   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(org_id, user_id)
);

-- Projects (one org can have multiple projects)
CREATE TABLE projects (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID REFERENCES organizations(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  project_number  TEXT,
  client          TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Reports (one row per uploaded PDF)
CREATE TABLE reports (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id       UUID REFERENCES projects(id) ON DELETE CASCADE,
  report_number    TEXT NOT NULL,
  report_type      TEXT NOT NULL DEFAULT 'concrete_compressive_strength',
  service_date     DATE,
  report_date      DATE,
  task             TEXT,
  pdf_storage_path TEXT NOT NULL,
  status           TEXT CHECK (status IN ('uploading', 'processing', 'ready', 'error')) DEFAULT 'uploading',
  error_message    TEXT,
  revision_number  INT DEFAULT 0,
  superseded_by    UUID REFERENCES reports(id),
  parsed_data      JSONB,
  uploaded_by      UUID REFERENCES auth.users(id),
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Sample sets (a single PDF can contain multiple sample sets)
CREATE TABLE sample_sets (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id                   UUID REFERENCES reports(id) ON DELETE CASCADE,
  set_number                  INT NOT NULL,
  -- Material
  mix_id                      TEXT,
  supplier                    TEXT,
  batch_time                  TEXT,
  truck_number                TEXT,
  plant                       TEXT,
  ticket_number               TEXT,
  specified_strength_psi      INT,
  strength_age_days           INT,
  -- Field test results
  slump_result                NUMERIC,
  slump_spec_min              NUMERIC,
  slump_spec_max              NUMERIC,
  air_content_result          NUMERIC,
  air_content_spec_min        NUMERIC,
  air_content_spec_max        NUMERIC,
  concrete_temp_result        NUMERIC,
  concrete_temp_spec_max      NUMERIC,
  ambient_temp                NUMERIC,
  plastic_unit_weight         NUMERIC,
  yield_cu_yds                NUMERIC,
  -- Sample info
  sample_date                 DATE,
  sample_time                 TEXT,
  sampled_by                  TEXT,
  weather_conditions          TEXT,
  accumulative_yards          NUMERIC,
  batch_size_cy               NUMERIC,
  placement_method            TEXT,
  water_added_before_gal      NUMERIC DEFAULT 0,
  water_added_after_gal       NUMERIC DEFAULT 0,
  sample_location             TEXT,
  placement_location          TEXT,
  sample_description          TEXT,
  -- Computed
  avg_28_day_strength_psi     NUMERIC,
  initial_cure                TEXT,
  final_cure                  TEXT,
  comments                    TEXT,
  created_at                  TIMESTAMPTZ DEFAULT NOW()
);

-- Individual cylinders per sample set
CREATE TABLE cylinders (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sample_set_id       UUID REFERENCES sample_sets(id) ON DELETE CASCADE,
  spec_id             TEXT,
  cylinder_condition  TEXT,
  avg_diameter_in     NUMERIC,
  area_sq_in          NUMERIC,
  date_received       DATE,
  date_tested         DATE,
  age_at_test_days    INT,
  max_load_lbs        NUMERIC,
  comp_strength_psi   NUMERIC,
  frac_type           TEXT,
  tested_by           TEXT
);

-- Compliance flags
CREATE TABLE flags (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  report_id           UUID REFERENCES reports(id) ON DELETE CASCADE,
  sample_set_id       UUID REFERENCES sample_sets(id),
  cylinder_id         UUID REFERENCES cylinders(id),
  flag_code           TEXT NOT NULL,
  severity            TEXT CHECK (severity IN ('critical', 'warning', 'info')) NOT NULL,
  description         TEXT NOT NULL,
  standard_reference  TEXT,
  field_name          TEXT,
  field_value         TEXT,
  spec_value          TEXT,
  status              TEXT CHECK (status IN ('active', 'acknowledged', 'disputed', 'resolved'))
                      DEFAULT 'active',
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Audit log for flag actions
CREATE TABLE flag_events (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  flag_id     UUID REFERENCES flags(id) ON DELETE CASCADE,
  user_id     UUID REFERENCES auth.users(id),
  action      TEXT NOT NULL,
  note        TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Row Level Security
ALTER TABLE organizations        ENABLE ROW LEVEL SECURITY;
ALTER TABLE organization_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects             ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports              ENABLE ROW LEVEL SECURITY;
ALTER TABLE sample_sets          ENABLE ROW LEVEL SECURITY;
ALTER TABLE cylinders            ENABLE ROW LEVEL SECURITY;
ALTER TABLE flags                ENABLE ROW LEVEL SECURITY;
ALTER TABLE flag_events          ENABLE ROW LEVEL SECURITY;

-- RLS policy helper
CREATE OR REPLACE FUNCTION user_org_ids()
RETURNS SETOF UUID LANGUAGE sql STABLE AS $$
  SELECT org_id FROM organization_members WHERE user_id = auth.uid()
$$;

-- RLS policies
CREATE POLICY "members can view their org" ON organizations
  FOR SELECT USING (id IN (SELECT user_org_ids()));

CREATE POLICY "members can insert org" ON organizations
  FOR INSERT WITH CHECK (true);

CREATE POLICY "members can view their org_members" ON organization_members
  FOR SELECT USING (org_id IN (SELECT user_org_ids()));

CREATE POLICY "members can insert org_members" ON organization_members
  FOR INSERT WITH CHECK (org_id IN (SELECT user_org_ids()));

CREATE POLICY "admins can update org_members" ON organization_members
  FOR UPDATE USING (org_id IN (SELECT user_org_ids()));

CREATE POLICY "admins can delete org_members" ON organization_members
  FOR DELETE USING (org_id IN (SELECT user_org_ids()));

CREATE POLICY "members can view their projects" ON projects
  FOR SELECT USING (org_id IN (SELECT user_org_ids()));

CREATE POLICY "members can insert projects" ON projects
  FOR INSERT WITH CHECK (org_id IN (SELECT user_org_ids()));

CREATE POLICY "members can view their reports" ON reports
  FOR SELECT USING (
    project_id IN (SELECT id FROM projects WHERE org_id IN (SELECT user_org_ids()))
  );

CREATE POLICY "members can insert reports" ON reports
  FOR INSERT WITH CHECK (
    project_id IN (SELECT id FROM projects WHERE org_id IN (SELECT user_org_ids()))
  );

CREATE POLICY "members can update reports" ON reports
  FOR UPDATE USING (
    project_id IN (SELECT id FROM projects WHERE org_id IN (SELECT user_org_ids()))
  );

CREATE POLICY "members can view sample_sets" ON sample_sets
  FOR SELECT USING (
    report_id IN (
      SELECT r.id FROM reports r
      JOIN projects p ON r.project_id = p.id
      WHERE p.org_id IN (SELECT user_org_ids())
    )
  );

CREATE POLICY "members can insert sample_sets" ON sample_sets
  FOR INSERT WITH CHECK (
    report_id IN (
      SELECT r.id FROM reports r
      JOIN projects p ON r.project_id = p.id
      WHERE p.org_id IN (SELECT user_org_ids())
    )
  );

CREATE POLICY "members can view cylinders" ON cylinders
  FOR SELECT USING (
    sample_set_id IN (
      SELECT ss.id FROM sample_sets ss
      JOIN reports r ON ss.report_id = r.id
      JOIN projects p ON r.project_id = p.id
      WHERE p.org_id IN (SELECT user_org_ids())
    )
  );

CREATE POLICY "members can insert cylinders" ON cylinders
  FOR INSERT WITH CHECK (
    sample_set_id IN (
      SELECT ss.id FROM sample_sets ss
      JOIN reports r ON ss.report_id = r.id
      JOIN projects p ON r.project_id = p.id
      WHERE p.org_id IN (SELECT user_org_ids())
    )
  );

CREATE POLICY "members can view flags" ON flags
  FOR SELECT USING (
    report_id IN (
      SELECT r.id FROM reports r
      JOIN projects p ON r.project_id = p.id
      WHERE p.org_id IN (SELECT user_org_ids())
    )
  );

CREATE POLICY "members can insert flags" ON flags
  FOR INSERT WITH CHECK (
    report_id IN (
      SELECT r.id FROM reports r
      JOIN projects p ON r.project_id = p.id
      WHERE p.org_id IN (SELECT user_org_ids())
    )
  );

CREATE POLICY "members can update flags" ON flags
  FOR UPDATE USING (
    report_id IN (
      SELECT r.id FROM reports r
      JOIN projects p ON r.project_id = p.id
      WHERE p.org_id IN (SELECT user_org_ids())
    )
  );

CREATE POLICY "members can view flag_events" ON flag_events
  FOR SELECT USING (
    flag_id IN (
      SELECT f.id FROM flags f
      JOIN reports r ON f.report_id = r.id
      JOIN projects p ON r.project_id = p.id
      WHERE p.org_id IN (SELECT user_org_ids())
    )
  );

CREATE POLICY "members can insert flag_events" ON flag_events
  FOR INSERT WITH CHECK (
    flag_id IN (
      SELECT f.id FROM flags f
      JOIN reports r ON f.report_id = r.id
      JOIN projects p ON r.project_id = p.id
      WHERE p.org_id IN (SELECT user_org_ids())
    )
  );
