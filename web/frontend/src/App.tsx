import '@gravity-ui/uikit/styles/fonts.css';
import '@gravity-ui/uikit/styles/styles.css';
import './App.css';

import type {Graph, TBlock, TConnection} from '@gravity-ui/graph';
import {EAnchorType, ECanDrag, GraphState} from '@gravity-ui/graph';
import {GraphBlock, GraphCanvas, useGraph} from '@gravity-ui/graph/react';
import {AbbrSql, Moon, Sun} from '@gravity-ui/icons';
import {AsideHeader} from '@gravity-ui/navigation';
import {Button, Icon, Theme, ThemeProvider} from '@gravity-ui/uikit';
import React from 'react';

type DDLObject = {
    name: string;
    type: string;
    schema: string;
    temporary?: boolean;
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

type GraphBlockMeta = {
    objectType: string;
    schema: string;
    columns: number;
    temporary: boolean;
};

type LineageGraphBlock = TBlock<GraphBlockMeta>;

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
    const [theme, setTheme] = React.useState<Theme>('light');
    const [compact, setCompact] = React.useState(true);
    const [ddl, setDdl] = React.useState(sampleDDL);
    const [result, setResult] = React.useState<AnalysisResult | null>(null);
    const [mermaid, setMermaid] = React.useState('');
    const [error, setError] = React.useState('');
    const [loading, setLoading] = React.useState(false);
    const [projects, setProjects] = React.useState<ProjectSummary[]>([]);
    const [projectName, setProjectName] = React.useState('');
    const isDark = theme === 'dark';

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
        <ThemeProvider theme={theme}>
            <AsideHeader
                compact={compact}
                onChangeCompact={setCompact}
                hideCollapseButton={false}
                logo={{icon: AbbrSql, text: 'DDL Lineage'}}
                renderFooter={() => (
                    <div className="sidebar-footer">
                        <Button
                            size="l"
                            view="flat"
                            title={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
                            onClick={() => setTheme(isDark ? 'light' : 'dark')}
                        >
                            <Icon data={isDark ? Sun : Moon} />
                        </Button>
                    </div>
                )}
                renderContent={() => (
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
                                                        <td>
                                                            {object.schema
                                                                ? `${object.schema}.${object.name}`
                                                                : object.name}
                                                            {object.temporary && (
                                                                <span className="temp-badge">TEMP</span>
                                                            )}
                                                        </td>
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
                                    <h2>Graph</h2>
                                    <LineageGraph result={result} />
                                </section>

                                <section className="panel">
                                    <h2>Mermaid Source</h2>
                                    <pre>{mermaid || 'graph LR'}</pre>
                                </section>
                            </div>
                        </section>
                    </main>
                )}
            />
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

const LineageGraph = ({result}: {result: AnalysisResult | null}) => {
    const graphConfig = React.useMemo(
        () => ({
            settings: {
                canDragCamera: true,
                canZoomCamera: true,
                canCreateNewConnections: false,
                canDrag: ECanDrag.ALL,
                useBlocksAnchors: true,
                showConnectionArrows: true,
                showConnectionLabels: true,
                useBezierConnections: true,
                bezierConnectionDirection: 'horizontal' as const,
            },
        }),
        [],
    );
    const {graph, setEntities, start} = useGraph(graphConfig);

    const graphEntities = React.useMemo(() => buildGraphEntities(result), [result]);

    React.useEffect(() => {
        setEntities(graphEntities);
        window.requestAnimationFrame(() => {
            graph.zoomTo('center', {padding: 160});
        });
    }, [graph, graphEntities, setEntities]);

    const renderBlock = React.useCallback((currentGraph: Graph, block: TBlock) => {
        const typedBlock = block as LineageGraphBlock;
        const meta = typedBlock.meta;

        return (
            <GraphBlock
                graph={currentGraph}
                block={typedBlock}
                className={`lineage-node${meta?.temporary ? ' lineage-node--temporary' : ''}`}
            >
                <div className={`lineage-node__type type-${meta?.objectType.toLowerCase()}`}>
                    {meta?.objectType || 'OBJECT'}
                </div>
                {meta?.temporary && <div className="lineage-node__temp">TEMP</div>}
                <div className="lineage-node__name">{typedBlock.name}</div>
                <div className="lineage-node__meta">
                    {meta?.schema ? `${meta.schema} · ` : ''}
                    {meta?.columns ?? 0} columns
                </div>
            </GraphBlock>
        );
    }, []);

    if (!result) {
        return <div className="graph-empty">Run analysis to render the graph.</div>;
    }

    return (
        <div className="lineage-graph">
            <GraphCanvas
                graph={graph}
                renderBlock={renderBlock}
                onStateChanged={({state}) => {
                    if (state === GraphState.ATTACHED) {
                        start();
                        graph.zoomTo('center', {padding: 160});
                    }
                }}
            />
        </div>
    );
};

function buildGraphEntities(result: AnalysisResult | null): {
    blocks: LineageGraphBlock[];
    connections: TConnection[];
} {
    if (!result) {
        return {blocks: [], connections: []};
    }

    const levelByName = computeLevels(result);
    const lanes = new Map<number, number>();
    const blockWidth = 190;
    const blockHeight = 96;
    const horizontalGap = 270;
    const verticalGap = 138;

    const blocks = result.objects.map((object) => {
        const level = levelByName.get(object.name) ?? 0;
        const lane = lanes.get(level) ?? 0;
        lanes.set(level, lane + 1);

        return {
            id: object.name,
            is: 'lineage-object',
            x: level * horizontalGap,
            y: lane * verticalGap,
            width: blockWidth,
            height: blockHeight,
            name: object.name,
            anchors: [
                {
                    id: `${object.name}-in`,
                    blockId: object.name,
                    type: EAnchorType.IN,
                    index: 0,
                },
                {
                    id: `${object.name}-out`,
                    blockId: object.name,
                    type: EAnchorType.OUT,
                    index: 0,
                },
            ],
            meta: {
                objectType: object.type,
                schema: object.schema,
                columns: object.columns.length,
                temporary: Boolean(object.temporary),
            },
        };
    });

    const objectNames = new Set(result.objects.map((object) => object.name));
    const connections = result.edges
        .filter((edge) => objectNames.has(edge.source) && objectNames.has(edge.target))
        .map((edge, index) => ({
            id: `${edge.type}-${edge.target}-${edge.source}-${index}`,
            sourceBlockId: edge.target,
            sourceAnchorId: `${edge.target}-out`,
            targetBlockId: edge.source,
            targetAnchorId: `${edge.source}-in`,
            label: edge.details ? `${edge.type} ${edge.details}` : edge.type,
            styles: edgeStyles(edge.type),
        }));

    return {blocks, connections};
}

function computeLevels(result: AnalysisResult): Map<string, number> {
    const names = result.objects.map((object) => object.name);
    const incoming = new Map(names.map((name) => [name, 0]));
    const dependents = new Map<string, string[]>();

    result.edges.forEach((edge) => {
        if (!incoming.has(edge.source) || !incoming.has(edge.target)) {
            return;
        }

        incoming.set(edge.source, (incoming.get(edge.source) || 0) + 1);
        dependents.set(edge.target, [...(dependents.get(edge.target) || []), edge.source]);
    });

    const queue = names.filter((name) => incoming.get(name) === 0);
    const levels = new Map(queue.map((name) => [name, 0]));

    while (queue.length) {
        const current = queue.shift() as string;
        const nextLevel = (levels.get(current) || 0) + 1;

        (dependents.get(current) || []).forEach((dependent) => {
            levels.set(dependent, Math.max(levels.get(dependent) || 0, nextLevel));
            incoming.set(dependent, (incoming.get(dependent) || 0) - 1);

            if (incoming.get(dependent) === 0) {
                queue.push(dependent);
            }
        });
    }

    names.forEach((name, index) => {
        if (!levels.has(name)) {
            levels.set(name, Math.floor(index / 4));
        }
    });

    return levels;
}

function edgeStyles(type: string): TConnection['styles'] {
    if (type === 'WRITE') {
        return {background: '#b54708', selectedBackground: '#93370d'};
    }

    if (type === 'READ') {
        return {background: '#0b65d8', selectedBackground: '#084b83'};
    }

    if (type === 'INHERITS') {
        return {background: '#3f7b1f', selectedBackground: '#2f5d16', dashes: [8, 6]};
    }

    return {background: '#626a76', selectedBackground: '#394150', dashes: [6, 5]};
}
