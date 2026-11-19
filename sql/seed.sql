USE NovaWarehouse;
GO

INSERT INTO dim.department (department_id, department_name)
VALUES
    ('DEPT-OPS', 'Operations'),
    ('DEPT-FIN', 'Finance'),
    ('DEPT-HR',  'HR'),
    ('DEPT-IT',  'IT'),
    ('DEPT-SEC', 'Security');

INSERT INTO dim.unit (unit_id, unit_name, department_id)
VALUES
    ('UNIT-TEL', 'Telemetry',       'DEPT-OPS'),
    ('UNIT-AUD', 'Audit & Ledger',  'DEPT-FIN'),
    ('UNIT-FLD', 'Field Personnel', 'DEPT-HR'),
    ('UNIT-INF', 'Core Systems',    'DEPT-IT'),
    ('UNIT-SOC', 'Access & CV Ops', 'DEPT-SEC');

INSERT INTO dim.role (role_id, role_name)
VALUES
    ('ROLE-ADM',  'Admin'),
    ('ROLE-TMGR', 'Telemetry Manager'),
    ('ROLE-AUD',  'Auditor'),
    ('ROLE-OPR',  'Operative'),
    ('ROLE-INT',  'Intern');

INSERT INTO dim.employee (employee_id, username, department_id, unit_id, role_id, manager_id, telemetry_manager_id)
VALUES
    ('EMP-001', 'nova_admin',      'DEPT-OPS', NULL,       'ROLE-ADM',  NULL,      NULL),
    ('EMP-002', 'telemetry_mgr_1', 'DEPT-OPS', 'UNIT-TEL', 'ROLE-TMGR', 'EMP-001', NULL),
    ('EMP-003', 'operative_1',     'DEPT-HR',  'UNIT-FLD', 'ROLE-OPR',  'EMP-002', 'EMP-002'),
    ('EMP-004', 'operative_2',     'DEPT-HR',  'UNIT-FLD', 'ROLE-OPR',  'EMP-002', 'EMP-002'),
    ('EMP-005', 'intern_1',        'DEPT-HR',  'UNIT-FLD', 'ROLE-INT',  'EMP-003', NULL),
    ('EMP-006', 'finance_auditor', 'DEPT-FIN', 'UNIT-AUD', 'ROLE-AUD',  'EMP-001', NULL);

INSERT INTO dim.asset (asset_id, asset_name, asset_type, department_id, assigned_operative_id)
VALUES
    ('ASSET-CMP-01', 'Compressor Train Alpha', 'Compressor',        'DEPT-OPS', 'EMP-003'),
    ('ASSET-CMP-02', 'Compressor Train Beta',  'Compressor',        'DEPT-OPS', 'EMP-004'),
    ('ASSET-SEC-01', 'Perimeter Auth Gateway', 'Security Node',     'DEPT-SEC', 'EMP-003'),
    ('ASSET-IT-01',  'Core Telemetry Broker',  'IT Infrastructure', 'DEPT-IT',  'EMP-004');
GO