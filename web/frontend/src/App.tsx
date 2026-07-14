import '@gravity-ui/uikit/styles/fonts.css';
import '@gravity-ui/uikit/styles/styles.css';
import './App.css';

import {ThemeProvider} from '@gravity-ui/uikit';
import {AsideHeader} from '@gravity-ui/navigation';
import React from 'react';

type DDLObject = {
    name: string;
    type: string;
    schema: string;
    columns: Array<{
        name: string;
        type: string;
        nullable: boolean;
        pk: boolean;
        fk_to: string;
        unique: boolean;
        default: string;
    }>;
};

type LineageEdge = {
    source: string;
    target: string;
    type: string;
    via: string;
    details: string;
};

type AnalysisResult = {
    objects: DDLObject[];
    edges: LineageEdge[];
    cycles: string[][];
    topo_order: string[];
    stats: {
        total_objects: number;
        total_edges: number;
        has_cycles: boolean;
    };
};

type AnalyzeResponse = {
    success: boolean;
    data?: AnalysisResult;
    mermaid?: string;
    error?: string | null;
};

type ProjectSummary = {
    project_name: string;
    display_name: string;
    description: string;
    updated_at: string;
    has_state: boolean;
};

const sampleDDL = `CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    status VARCHAR(50) DEFAULT 'pending'
);

CREATE VIEW active_orders AS
    SELECT o.id, u.email
    FROM orders o
    JOIN users u ON o.user_id = u.id
    WHERE o.status = 'active';`;

export const App = () => {
    const [ddl, setDdl] = React.useState(sampleDDL);
    const [result, setResult] = React.useState<AnalysisResult | null>(null);
    const [mermaid, setMermaid] = React.useState('');
    const [error, setError] = React.useState('');
    const [loading, setLoading] = React.useState(false);
    const [projects, setProjects] = React.useState<ProjectSummary[]>([]);
    const [projectName, setProjectName] = React.useState('');

    const loadProjects = React.useCallback(async () => {
        try {
            const response = await fetch('/api/projects');
            const payload = await response.json();
            if (payload.success) {
                setProjects(payload.projects);
            }
        } catch {
            setProjects([]);
        }
    }, []);

    React.useEffect(() => {
        loadProjects();
    }, [loadProjects]);

    const analyze = async () => {
        setLoading(true);
        setError('');

        try {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    ddl,
                    project_name: projectName.trim() || undefined,
                }),
            });
            const payload = (await response.json()) as AnalyzeResponse;

            if (!response.ok || !payload.success || !payload.data) {
                throw new Error(payload.error || 'Analysis failed');
            }

            setResult(payload.data);
            setMermaid(payload.mermaid || '');
            await loadProjects();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unexpected error');
        } finally {
            setLoading(false);
        }
    };

    const loadProject = async (name: string) => {
        if (!name) {
            return;
        }

        setError('');
        try {
            const response = await fetch(`/api/project/${encodeURIComponent(name)}`);
            const payload = await response.json();
            if (!response.ok || !payload.success) {
                throw new Error(payload.error || 'Project load failed');
            }

            setProjectName(name);
            setDdl(payload.project?.ddl || sampleDDL);
            setResult(payload.project?.analysis || null);
            setMermaid(payload.project?.mermaid || '');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unexpected error');
        }
    };

    return (
        <ThemeProvider theme="light">
            <main className="app-shell">
                
                <header className="topbar">
                    <div>
                        <h1>DDL Lineage Analyzer</h1>
                        <p>Tables, dependencies, cycles and execution order from SQL DDL.</p>
                    </div>
                    <div className="project-controls">
                        <input
                            value={projectName}
                            onChange={(event) => setProjectName(event.target.value)}
                            placeholder="Project name"
                            aria-label="Project name"
                        />
                        <select
                            value=""
                            onChange={(event) => loadProject(event.target.value)}
                            aria-label="Load project"
                        >
                            <option value="">Load project</option>
                            {projects.map((project) => (
                                <option key={project.project_name} value={project.project_name}>
                                    {project.display_name}
                                </option>
                            ))}
                        </select>
                    </div>
                </header>

                <section className="workspace">
                    <div className="editor-pane">
                        <div className="pane-header">
                            <h2>DDL</h2>
                            <button type="button" onClick={analyze} disabled={loading || !ddl.trim()}>
                                {loading ? 'Analyzing...' : 'Analyze'}
                            </button>
                        </div>
                        <textarea
                            value={ddl}
                            onChange={(event) => setDdl(event.target.value)}
                            spellCheck={false}
                            aria-label="DDL input"
                        />
                        {error && <div className="error">{error}</div>}
                    </div>

                    <div className="results-pane">
                        <div className="stats-grid">
                            <Metric label="Objects" value={result?.stats.total_objects ?? 0} />
                            <Metric label="Edges" value={result?.stats.total_edges ?? 0} />
                            <Metric label="Cycles" value={result?.cycles.length ?? 0} />
                        </div>

                        <section className="panel">
                            <h2>Objects</h2>
                            <div className="table-wrap">
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Name</th>
                                            <th>Type</th>
                                            <th>Columns</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {(result?.objects || []).map((object) => (
                                            <tr key={`${object.type}-${object.name}`}>
                                                <td>{object.schema ? `${object.schema}.${object.name}` : object.name}</td>
                                                <td>{object.type}</td>
                                                <td>{object.columns.length}</td>
                                            </tr>
                                        ))}
                                        {!result && <EmptyRow colSpan={3} />}
                                    </tbody>
                                </table>
                            </div>
                        </section>

                        <section className="panel">
                            <h2>Relationships</h2>
                            <div className="table-wrap">
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Source</th>
                                            <th>Type</th>
                                            <th>Target</th>
                                            <th>Details</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {(result?.edges || []).map((edge, index) => (
                                            <tr key={`${edge.source}-${edge.target}-${edge.type}-${index}`}>
                                                <td>{edge.source}</td>
                                                <td>
                                                    <span className={`edge edge-${edge.type.toLowerCase()}`}>
                                                        {edge.type}
                                                    </span>
                                                </td>
                                                <td>{edge.target}</td>
                                                <td>{edge.details || edge.via || '-'}</td>
                                            </tr>
                                        ))}
                                        {!result && <EmptyRow colSpan={4} />}
                                    </tbody>
                                </table>
                            </div>
                        </section>

                        <section className="panel">
                            <h2>Execution Order</h2>
                            <p className="order-line">
                                {result?.topo_order.length ? result.topo_order.join(' -> ') : 'No analysis yet'}
                            </p>
                        </section>

                        <section className="panel">
                            <h2>Mermaid</h2>
                            <pre>{mermaid || 'graph LR'}</pre>
                        </section>
                    </div>
                </section>
            </main>
        </ThemeProvider>
    );
};

const Metric = ({label, value}: {label: string; value: number}) => (
    <div className="metric">
        <span>{label}</span>
        <strong>{value}</strong>
    </div>
);

const EmptyRow = ({colSpan}: {colSpan: number}) => (
    <tr>
        <td colSpan={colSpan} className="empty">
            Run analysis to populate this table.
        </td>
    </tr>
);
