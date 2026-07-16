import '@gravity-ui/uikit/styles/fonts.css';
import '@gravity-ui/uikit/styles/styles.css';
import './App.css';

import type {Graph, TBlock, TBlockGeometrySnapshot, TConnection, TGraphColors} from '@gravity-ui/graph';
import {EAnchorType, ECanDrag, GraphState, useLayeredLayout} from '@gravity-ui/graph';
import type {UseLayeredLayoutParams} from '@gravity-ui/graph';
import {GraphBlock, GraphCanvas, useGraph} from '@gravity-ui/graph/react';
import {ArrowsExpand, ChevronLeft, ChevronRight, ChevronsCollapseUpRight, ClockArrowRotateLeft, Database, Folder, Moon, Plus, Sun} from '@gravity-ui/icons';
import {AsideHeader} from '@gravity-ui/navigation';
import {Button, Icon, Theme, ThemeProvider, Toaster, ToasterComponent, ToasterProvider, useToaster} from '@gravity-ui/uikit';
import {ConnectionsPanel} from './ConnectionsPanel';
import {HistoryPanel} from './HistoryPanel';
import {ProjectsPanel} from './ProjectsPanel';
import Editor from '@monaco-editor/react';
import React from 'react';
import {format as formatSql} from 'sql-formatter';
import {ProjectSummary, AnalysisResult, LineageGraphBlock, AnalyzeResponse, SavedConnection, ConnectFormData} from './types';


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

const toasterInstance = new Toaster();

export const App = () => {
    const [theme, setTheme] = React.useState<Theme>('light');
    return (
        <ThemeProvider theme={theme}>
            <ToasterProvider toaster={toasterInstance}>
                <AppContent theme={theme} setTheme={setTheme} />
                <ToasterComponent />
            </ToasterProvider>
        </ThemeProvider>
    );
};

const AppContent = ({theme, setTheme}: {theme: Theme; setTheme: (t: Theme) => void}) => {
    const {add: addToast} = useToaster();
    const [compact, setCompact] = React.useState(true);
    const [ddl, setDdl] = React.useState(sampleDDL);
    const [result, setResult] = React.useState<AnalysisResult | null>(null);
    const [mermaid, setMermaid] = React.useState('');
    const [error, setError] = React.useState('');
    const [loading, setLoading] = React.useState(false);
    const [projects, setProjects] = React.useState<ProjectSummary[]>([]);
    const [projectName, setProjectName] = React.useState('');
    const [isMermaidOpen, setIsMermaidOpen] = React.useState(false);
    const [lastAnalyzedDdl, setLastAnalyzedDdl] = React.useState<string | null>(null);
    const [activePanel, setActivePanel] = React.useState<'projects' | 'connections' | 'history' | null>(null);
    const [editorCollapsed, setEditorCollapsed] = React.useState(false);
    const [scanning, setScanning] = React.useState(false);
    const [scanError, setScanError] = React.useState('');
    const [savedConnections, setSavedConnections] = React.useState<SavedConnection[]>(() => {
        try {
            return JSON.parse(localStorage.getItem('ddl-lineage-connections') || '[]');
        } catch {
            return [];
        }
    });
    const isDark = theme === 'dark';
    const hasChanges = ddl.trim() !== '' && ddl !== lastAnalyzedDdl;

    const persistConnections = (conns: SavedConnection[]) => {
        setSavedConnections(conns);
        localStorage.setItem('ddl-lineage-connections', JSON.stringify(conns));
    };

    const togglePanel = (panel: 'projects' | 'connections' | 'history') => {
        setActivePanel((prev) => (prev === panel ? null : panel));
    };

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
        if (loading || !ddl.trim()) return;
        setLoading(true);
        setError('');
        try {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ddl, project_name: projectName.trim() || undefined}),
            });
            const payload = (await response.json()) as AnalyzeResponse;
            if (!response.ok || !payload.success || !payload.data) {
                throw new Error(payload.error || 'Analysis failed');
            }
            setResult(payload.data);
            setMermaid(payload.mermaid || '');
            setLastAnalyzedDdl(ddl);
            await loadProjects();
            const {total_objects, total_edges} = payload.data.stats;
            const cycleCount = payload.data.cycles.length;
            addToast({
                name: 'analysis-done',
                theme: cycleCount > 0 ? 'warning' : 'success',
                title: 'Analysis complete',
                content: `${total_objects} objects · ${total_edges} edges${cycleCount > 0 ? ` · ${cycleCount} cycle${cycleCount > 1 ? 's' : ''} detected` : ''}`,
                autoHiding: 4000,
            });
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unexpected error');
        } finally {
            setLoading(false);
        }
    };

    const loadProject = async (name: string) => {
        if (!name) return;
        setError('');
        try {
            const response = await fetch(`/api/project/${encodeURIComponent(name)}`);
            const payload = await response.json();
            if (!response.ok || !payload.success) {
                throw new Error(payload.error || 'Project load failed');
            }
            setProjectName(name);
            const loadedDdl = payload.project?.ddl || sampleDDL;
            setDdl(loadedDdl);
            setResult(payload.project?.analysis || null);
            setMermaid(payload.project?.mermaid || '');
            setLastAnalyzedDdl(payload.project?.analysis ? loadedDdl : null);
            addToast({
                name: 'project-loaded',
                theme: 'info',
                title: 'Project loaded',
                content: name,
                autoHiding: 2500,
            });
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unexpected error');
        }
    };

    const formatDdl = () => {
        try {
            setDdl(formatSql(ddl, {language: 'postgresql'}));
            setError('');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unable to format SQL');
        }
    };

    const clearAll = () => {
        setDdl('');
        setResult(null);
        setMermaid('');
        setError('');
        setProjectName('');
        setLastAnalyzedDdl(null);
    };

    const handleScan = async (form: ConnectFormData) => {
        setScanning(true);
        setScanError('');
        try {
            const response = await fetch('/api/connect', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    type: form.type,
                    host: form.host,
                    port: form.port || undefined,
                    database: form.database,
                    schema: form.schema || undefined,
                    username: form.username,
                    password: form.password,
                    project_name: projectName.trim() || undefined,
                }),
            });
            const payload = await response.json();
            if (!response.ok || !payload.success) {
                throw new Error(payload.error || 'Connection failed');
            }
            setDdl(payload.ddl);
            setResult(null);
            setMermaid('');
            setError('');
            if (editorCollapsed) setEditorCollapsed(false);
            const lineCount = payload.ddl.split('\n').length;
            addToast({
                name: 'scan-done',
                theme: 'success',
                title: 'Database scanned',
                content: `DDL extracted — ${lineCount} lines. Click Analyze to build the graph.`,
                autoHiding: 5000,
            });
        } catch (err) {
            const msg = err instanceof Error ? err.message : 'Connection failed';
            setScanError(msg);
            addToast({name: 'scan-error', theme: 'danger', title: 'Scan failed', content: msg, autoHiding: 5000});
        } finally {
            setScanning(false);
        }
    };

    const handleRestoreVersion = async (name: string, id: number) => {
        setError('');
        try {
            const response = await fetch(
                `/api/project/${encodeURIComponent(name)}/history/${id}`,
            );
            const payload = await response.json();
            if (!response.ok || !payload.success) {
                throw new Error(payload.error || 'Restore failed');
            }
            const project = payload.project;
            const restoredDdl = project?.ddl || sampleDDL;
            setDdl(restoredDdl);
            setResult(project?.analysis || null);
            setMermaid(project?.mermaid || '');
            setLastAnalyzedDdl(project?.analysis ? restoredDdl : null);
            addToast({
                name: 'version-restored',
                theme: 'success',
                title: 'Version restored',
                autoHiding: 2500,
            });
        } catch (err) {
            addToast({
                name: 'restore-error',
                theme: 'danger',
                title: 'Restore failed',
                content: err instanceof Error ? err.message : undefined,
                autoHiding: 3000,
            });
        }
    };

    const handleDeleteProject = async (name: string) => {
        try {
            const response = await fetch(`/api/project/${encodeURIComponent(name)}`, {method: 'DELETE'});
            const payload = await response.json();
            if (!response.ok || !payload.success) throw new Error(payload.error || 'Delete failed');
            setProjects(payload.projects || []);
            addToast({name: 'project-deleted', theme: 'normal', title: `Project "${name}" deleted`, autoHiding: 2500});
        } catch (err) {
            addToast({name: 'delete-error', theme: 'danger', title: 'Delete failed', autoHiding: 3000});
        }
    };

    const copyText = async (text: string, label: string) => {
        try {
            await navigator.clipboard.writeText(text);
            addToast({
                name: `copy-${label}`,
                theme: 'success',
                title: `${label} copied to clipboard`,
                autoHiding: 2000,
            });
        } catch {
            addToast({name: 'copy-error', theme: 'danger', title: 'Copy failed', autoHiding: 2000});
        }
    };

    React.useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                void analyze();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [ddl, loading, projectName]);

    return (
        <AsideHeader
            headerDecoration={true}
            compact={compact}
            onChangeCompact={setCompact}
            hideCollapseButton={false}
            logo={{
                iconSrc: `${process.env.PUBLIC_URL}/ddl-lineage-icon.svg`,
                text: 'DDL Lineage',
            }}
            menuItems={[
                {
                    id: 'projects',
                    title: 'Projects',
                    icon: Folder,
                    current: activePanel === 'projects',
                    onItemClick: () => togglePanel('projects'),
                },
                {
                    id: 'connections',
                    title: 'Connections',
                    icon: Database,
                    current: activePanel === 'connections',
                    onItemClick: () => togglePanel('connections'),
                },
                {
                    id: 'history',
                    title: 'History',
                    icon: ClockArrowRotateLeft,
                    current: activePanel === 'history',
                    onItemClick: () => togglePanel('history'),
                },
            ]}
            panelItems={[
                {
                    id: 'projects',
                    visible: activePanel === 'projects',
                    children: (
                        <ProjectsPanel
                            projects={projects}
                            projectName={projectName}
                            onProjectNameChange={setProjectName}
                            onLoad={(name) => {
                                void loadProject(name);
                                setActivePanel(null);
                            }}
                            onDelete={handleDeleteProject}
                        />
                    ),
                },
                {
                    id: 'connections',
                    visible: activePanel === 'connections',
                    children: (
                        <ConnectionsPanel
                            savedConnections={savedConnections}
                            scanning={scanning}
                            scanError={scanError}
                            onScan={handleScan}
                            onSave={(conn) => persistConnections([...savedConnections, conn])}
                            onDelete={(id) =>
                                persistConnections(savedConnections.filter((c) => c.id !== id))
                            }
                        />
                    ),
                },
                {
                    id: 'history',
                    visible: activePanel === 'history',
                    children: (
                        <HistoryPanel
                            projectName={projectName}
                            onRestoreVersion={handleRestoreVersion}
                        />
                    ),
                },
            ]}
            onClosePanel={() => setActivePanel(null)}
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
                        <div className="topbar-title">
                            <h1>DDL Lineage</h1>
                            {projectName && (
                                <>
                                    <span className="topbar-sep">/</span>
                                    <span className="topbar-project">{projectName}</span>
                                </>
                            )}
                        </div>
                    </header>

                    <section className={`workspace${editorCollapsed ? ' workspace--collapsed' : ''}`}>
                        <div className={`editor-pane${editorCollapsed ? ' editor-pane--collapsed' : ''}`}>
                            <div className="pane-header">
                                <h2>DDL</h2>
                                <div className="editor-actions">
                                    {!editorCollapsed && (
                                        <>
                                            <button
                                                type="button"
                                                className="btn-secondary btn-icon"
                                                title="New analysis"
                                                onClick={clearAll}
                                            >
                                                <Icon data={Plus} size={14} />
                                                New
                                            </button>
                                            <button
                                                type="button"
                                                className="btn-secondary"
                                                onClick={formatDdl}
                                                disabled={!ddl.trim()}
                                            >
                                                Format SQL
                                            </button>
                                            <button
                                                type="button"
                                                className={hasChanges ? undefined : 'btn-secondary'}
                                                title="Ctrl+Enter"
                                                onClick={() => void analyze()}
                                                disabled={loading || !ddl.trim()}
                                            >
                                                {loading ? 'Analyzing…' : 'Analyze'}
                                            </button>
                                        </>
                                    )}
                                    <button
                                        type="button"
                                        className="btn-secondary btn-collapse"
                                        title={editorCollapsed ? 'Expand editor' : 'Collapse editor'}
                                        onClick={() => setEditorCollapsed((v) => !v)}
                                    >
                                        <Icon
                                            data={editorCollapsed ? ChevronRight : ChevronLeft}
                                            size={14}
                                        />
                                    </button>
                                </div>
                            </div>
                            {!editorCollapsed && (
                                <>
                                    <div className="sql-editor">
                                        <Editor
                                            height="100%"
                                            language="sql"
                                            theme={isDark ? 'vs-dark' : 'vs'}
                                            value={ddl}
                                            onChange={(value) => setDdl(value || '')}
                                            options={{
                                                automaticLayout: true,
                                                minimap: {enabled: false},
                                                fontFamily: 'SFMono-Regular, Consolas, monospace',
                                                fontSize: 13,
                                                lineHeight: 20,
                                                scrollBeyondLastLine: false,
                                                tabSize: 4,
                                                wordWrap: 'on',
                                            }}
                                        />
                                    </div>
                                    {error && <div className="error">{error}</div>}
                                </>
                            )}
                        </div>

                        <div className={`results-pane${loading ? ' results-pane--loading' : ''}`}>
                            <div className="stats-grid">
                                <Metric label="Objects" value={result?.stats?.total_objects ?? 0} />
                                <Metric label="Edges" value={result?.stats?.total_edges ?? 0} />
                                <Metric
                                    label="Cycles"
                                    value={result?.cycles?.length ?? 0}
                                    variant={
                                        result
                                            ? (result.cycles?.length ?? 0) > 0
                                                ? 'danger'
                                                : 'success'
                                            : undefined
                                    }
                                />
                            </div>

                            <section className="panel">
                                <h2>Graph</h2>
                                <LineageGraph result={result} isDark={isDark} />
                            </section>

                            <section className="panel">
                                <h2>
                                    Objects
                                    {result && (
                                        <span className="panel-count">{result.objects.length}</span>
                                    )}
                                </h2>
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
                                                    <td>
                                                        <span
                                                            className={`edge type-${object.type.toLowerCase()}`}
                                                        >
                                                            {object.type}
                                                        </span>
                                                    </td>
                                                    <td>{object.columns.length}</td>
                                                </tr>
                                            ))}
                                            {!result && <EmptyRow colSpan={3} />}
                                        </tbody>
                                    </table>
                                </div>
                            </section>

                            <section className="panel">
                                <h2>
                                    Relationships
                                    {result && (
                                        <span className="panel-count">{result.edges.length}</span>
                                    )}
                                </h2>
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
                                                <tr
                                                    key={`${edge.source}-${edge.target}-${edge.type}-${index}`}
                                                >
                                                    <td>{edge.source}</td>
                                                    <td>
                                                        <span
                                                            className={`edge edge-${edge.type.toLowerCase()}`}
                                                        >
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
                                <div className="exec-order">
                                    {result?.topo_order?.length ? (
                                        result.topo_order.map((name, i) => (
                                            <React.Fragment key={name + i}>
                                                {i > 0 && <span className="exec-order__sep">→</span>}
                                                <span className="exec-order__step">{name}</span>
                                            </React.Fragment>
                                        ))
                                    ) : (
                                        <span className="exec-order__empty">No analysis yet</span>
                                    )}
                                </div>
                            </section>

                            <section className="panel">
                                <div className="collapsible-header">
                                    <h2>Export</h2>
                                    <div className="export-actions">
                                        <button
                                            type="button"
                                            className="btn-secondary"
                                            disabled={!mermaid}
                                            onClick={() => void copyText(mermaid, 'Mermaid')}
                                        >
                                            Copy Mermaid
                                        </button>
                                        <button
                                            type="button"
                                            className="btn-secondary"
                                            disabled={!result}
                                            onClick={() =>
                                                void copyText(JSON.stringify(result, null, 2), 'JSON')
                                            }
                                        >
                                            Copy JSON
                                        </button>
                                        <button
                                            type="button"
                                            className="btn-secondary"
                                            aria-expanded={isMermaidOpen}
                                            onClick={() => setIsMermaidOpen((open) => !open)}
                                        >
                                            {isMermaidOpen ? 'Hide preview' : 'Preview'}
                                        </button>
                                    </div>
                                </div>
                                {isMermaidOpen && <pre>{mermaid || 'graph LR'}</pre>}
                            </section>
                        </div>
                    </section>
                </main>
            )}
        />
    );
};

const Metric = ({
    label,
    value,
    variant,
}: {
    label: string;
    value: number;
    variant?: 'danger' | 'success';
}) => (
    <div className={`metric${variant ? ` metric--${variant}` : ''}`}>
        <span>{label}</span>
        <strong key={value}>{value}</strong>
    </div>
);

const EmptyRow = ({colSpan}: {colSpan: number}) => (
    <tr>
        <td colSpan={colSpan} className="empty">
            Run analysis to populate this table.
        </td>
    </tr>
);

const EDGE_LEGEND = [
    {type: 'FK', cls: 'edge-fk'},
    {type: 'READ', cls: 'edge-read'},
    {type: 'WRITE', cls: 'edge-write'},
    {type: 'INHERITS', cls: 'edge-inherits'},
] as const;

const LineageGraph = ({result, isDark}: {result: AnalysisResult | null; isDark: boolean}) => {
    const graphContainerRef = React.useRef<HTMLDivElement | null>(null);
    const [isFullscreen, setIsFullscreen] = React.useState(false);

    // User-dragged positions, reset when result changes
    const userPositionsRef = React.useRef<{
        forResult: AnalysisResult | null;
        map: Map<string, {x: number; y: number}>;
    }>({forResult: null, map: new Map()});

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

    React.useEffect(() => {
        graph.setColors(graphThemeColors(isDark));
    }, [graph, isDark]);

    // Block dimensions depend on object count
    const blockDims = React.useMemo(() => {
        const count = result?.objects.length ?? 0;
        return {
            width: count > 80 ? 150 : count > 32 ? 168 : 190,
            height: count > 80 ? 76 : count > 32 ? 84 : 96,
        };
    }, [result]);

    // Input for the built-in layered layout algorithm
    const layoutInput = React.useMemo((): UseLayeredLayoutParams => {
        if (!result) return {blocks: [], connections: []};
        const count = result.objects.length;
        const objNames = new Set(result.objects.map((o) => o.name));
        return {
            blocks: result.objects.map((obj) => ({
                id: obj.name,
                width: blockDims.width,
                height: blockDims.height,
            })),
            connections: result.edges
                .filter((e) => objNames.has(e.source) && objNames.has(e.target))
                .map((e, i) => ({
                    id: `layout-${i}`,
                    sourceBlockId: e.source,
                    targetBlockId: e.target,
                })),
            layoutOptions: {
                nodeHorizontalGap: count > 80 ? 48 : count > 32 ? 64 : 80,
                nodeVerticalGap: count > 80 ? 100 : count > 32 ? 116 : 136,
            },
        };
    }, [result, blockDims]);

    const {result: layoutResult, isLoading: layoutLoading} = useLayeredLayout(layoutInput);

    // Capture block positions when user drags them
    React.useEffect(() => {
        return graph.on(
            'blocks-geometry-change' as Parameters<typeof graph.on>[0],
            (e: CustomEvent<{blocks: TBlockGeometrySnapshot[]}>) => {
                const store = userPositionsRef.current;
                if (store.forResult !== result) {
                    userPositionsRef.current = {forResult: result, map: new Map()};
                }
                e.detail.blocks.forEach(({id, x, y}) => {
                    userPositionsRef.current.map.set(String(id), {x, y});
                });
            },
        );
    }, [graph, result]);

    // Build visual entities: layout positions + user overrides
    const graphEntities = React.useMemo(() => {
        if (!result) return {blocks: [] as LineageGraphBlock[], connections: [] as TConnection[]};

        const store = userPositionsRef.current;
        const savedPos = store.forResult === result ? store.map : new Map<string, {x: number; y: number}>();

        const blocks: LineageGraphBlock[] = result.objects.map((object) => {
            const pos =
                savedPos.get(object.name) ??
                layoutResult?.blocks?.[object.name] ??
                {x: 0, y: 0};
            return {
                id: object.name,
                is: 'lineage-object',
                x: pos.x,
                y: pos.y,
                width: blockDims.width,
                height: blockDims.height,
                name: object.name,
                anchors: [
                    {id: `${object.name}-in`, blockId: object.name, type: EAnchorType.IN, index: 0},
                    {id: `${object.name}-out`, blockId: object.name, type: EAnchorType.OUT, index: 0},
                ],
                meta: {
                    objectType: object.type,
                    schema: object.schema,
                    columns: object.columns.length,
                    fields: object.columns.map((c) => ({name: c.name, type: c.type})),
                    temporary: Boolean(object.temporary),
                },
            };
        });

        const objectNames = new Set(result.objects.map((o) => o.name));
        const connections: TConnection[] = result.edges
            .filter((e) => objectNames.has(e.source) && objectNames.has(e.target))
            .map((e, i) => ({
                id: `${e.type}-${e.target}-${e.source}-${i}`,
                sourceBlockId: e.target,
                sourceAnchorId: `${e.target}-out`,
                targetBlockId: e.source,
                targetAnchorId: `${e.source}-in`,
                label: e.details ? `${e.type} ${e.details}` : e.type,
                styles: edgeStyles(e.type, isDark),
            }));

        return {blocks, connections};
    }, [result, isDark, layoutResult, blockDims]);

    const blockIds = React.useMemo(
        () => graphEntities.blocks.map((block) => block.id),
        [graphEntities.blocks],
    );

    const fitGraph = React.useCallback(() => {
        window.requestAnimationFrame(() => {
            if (blockIds.length) {
                graph.zoomTo(blockIds, {padding: blockIds.length > 80 ? 48 : 96});
            } else {
                graph.zoomTo('center', {padding: 96});
            }
        });
    }, [blockIds, graph]);

    React.useEffect(() => {
        const handleFullscreenChange = () => {
            setIsFullscreen(document.fullscreenElement === graphContainerRef.current);
            fitGraph();
        };
        document.addEventListener('fullscreenchange', handleFullscreenChange);
        return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
    }, [fitGraph]);

    // Skip setEntities while layout is computing to avoid flickering to (0,0)
    React.useEffect(() => {
        if (layoutLoading && result !== null) return;
        setEntities(graphEntities);
        fitGraph();
    }, [fitGraph, graphEntities, setEntities, layoutLoading, result]);

    const toggleFullscreen = React.useCallback(async () => {
        if (!graphContainerRef.current) return;
        if (document.fullscreenElement === graphContainerRef.current) {
            await document.exitFullscreen();
            return;
        }
        await graphContainerRef.current.requestFullscreen();
    }, []);

    const renderBlock = React.useCallback((currentGraph: Graph, block: TBlock) => {
        const typedBlock = block as LineageGraphBlock;
        const meta = typedBlock.meta;
        const displayName = meta?.schema ? `${meta.schema}.${typedBlock.name}` : typedBlock.name;
        const objectType = meta?.objectType || 'OBJECT';
        const fields = meta?.fields || [];
        const visibleFields = fields.slice(0, 8);
        const hiddenFieldCount = Math.max(0, fields.length - visibleFields.length);

        return (
            <GraphBlock
                graph={currentGraph}
                block={typedBlock}
                className={`lineage-node${meta?.temporary ? ' lineage-node--temporary' : ''}`}
            >
                <div className="lineage-node__tooltip" role="tooltip">
                    <div className="lineage-node__tooltip-header">
                        <strong>{displayName}</strong>
                        <span>{objectType}</span>
                    </div>
                    <div className="lineage-node__tooltip-fields">
                        {visibleFields.length ? (
                            visibleFields.map((field) => (
                                <div
                                    key={`${typedBlock.id}-${field.name}`}
                                    className="lineage-node__tooltip-field"
                                >
                                    <span>{field.name}</span>
                                    <code>{field.type || 'unknown'}</code>
                                </div>
                            ))
                        ) : (
                            <div className="lineage-node__tooltip-empty">No fields detected</div>
                        )}
                        {hiddenFieldCount > 0 && (
                            <div className="lineage-node__tooltip-more">
                                +{hiddenFieldCount} more fields
                            </div>
                        )}
                    </div>
                </div>
                <div className={`lineage-node__type type-${meta?.objectType.toLowerCase()}`}>
                    {objectType}
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
        return (
            <div className="graph-empty">
                <div className="graph-empty__hint">
                    Enter DDL on the left and click <strong>Analyze</strong>
                </div>
            </div>
        );
    }

    const graphSizeClass =
        result.stats.total_objects > 80
            ? 'lineage-graph--dense'
            : result.stats.total_objects > 32
              ? 'lineage-graph--large'
              : '';

    return (
        <div ref={graphContainerRef} className={`lineage-graph ${graphSizeClass}`}>
            <div className="lineage-graph__toolbar">
                <div className="lineage-legend">
                    {EDGE_LEGEND.map(({type, cls}) => (
                        <span key={type} className={`edge ${cls}`}>
                            {type}
                        </span>
                    ))}
                </div>
                <div className="lineage-graph__actions">
                    <button type="button" onClick={fitGraph}>
                        Fit
                    </button>
                    <button
                        type="button"
                        aria-label={isFullscreen ? 'Exit fullscreen' : 'Open graph fullscreen'}
                        title={isFullscreen ? 'Exit fullscreen' : 'Open graph fullscreen'}
                        onClick={() => void toggleFullscreen()}
                    >
                        <Icon
                            data={isFullscreen ? ChevronsCollapseUpRight : ArrowsExpand}
                            size={16}
                        />
                    </button>
                </div>
            </div>
            <GraphCanvas
                className="lineage-graph__canvas"
                graph={graph}
                renderBlock={renderBlock}
                onStateChanged={({state}) => {
                    if (state === GraphState.ATTACHED) {
                        start();
                        fitGraph();
                    }
                }}
            />
        </div>
    );
};

function edgeStyles(type: string, isDark: boolean): TConnection['styles'] {
    if (type === 'WRITE') {
        return isDark
            ? {background: '#ff9d66', selectedBackground: '#ffb88a'}
            : {background: '#b54708', selectedBackground: '#93370d'};
    }
    if (type === 'READ') {
        return isDark
            ? {background: '#72b5ff', selectedBackground: '#a8d2ff'}
            : {background: '#0b65d8', selectedBackground: '#084b83'};
    }
    if (type === 'INHERITS') {
        return isDark
            ? {background: '#9bd36a', selectedBackground: '#b7e48e', dashes: [8, 6]}
            : {background: '#3f7b1f', selectedBackground: '#2f5d16', dashes: [8, 6]};
    }
    return isDark
        ? {background: '#b3bac6', selectedBackground: '#d0d5dd', dashes: [6, 5]}
        : {background: '#626a76', selectedBackground: '#394150', dashes: [6, 5]};
}

function graphThemeColors(isDark: boolean): TGraphColors {
    if (isDark) {
        return {
            canvas: {
                belowLayerBackground: '#111827',
                layerBackground: '#111827',
                dots: '#334155',
                border: '#334155',
            },
            block: {
                background: '#1f2937',
                border: '#475569',
                text: '#f8fafc',
                selectedBorder: '#72b5ff',
            },
            anchor: {
                background: '#94a3b8',
                selectedBorder: '#72b5ff',
            },
            connection: {
                background: '#94a3b8',
                selectedBackground: '#d0d5dd',
            },
            connectionLabel: {
                background: '#1f2937',
                hoverBackground: '#334155',
                selectedBackground: '#0f3b66',
                text: '#e5e7eb',
                hoverText: '#ffffff',
                selectedText: '#ffffff',
            },
            selection: {
                background: 'rgba(114, 181, 255, 0.18)',
                border: '#72b5ff',
            },
        };
    }

    return {
        canvas: {
            belowLayerBackground: '#f4f6f8',
            layerBackground: '#f4f6f8',
            dots: '#d8dee8',
            border: '#d8dee8',
        },
        block: {
            background: '#ffffff',
            border: '#d8dee8',
            text: '#1f2937',
            selectedBorder: '#0b65d8',
        },
        anchor: {
            background: '#7b8794',
            selectedBorder: '#0b65d8',
        },
        connection: {
            background: '#626a76',
            selectedBackground: '#394150',
        },
        connectionLabel: {
            background: '#ffffff',
            hoverBackground: '#f4f6f8',
            selectedBackground: '#dff0ff',
            text: '#394150',
            hoverText: '#1f2937',
            selectedText: '#084b83',
        },
        selection: {
            background: 'rgba(11, 101, 216, 0.12)',
            border: '#0b65d8',
        },
    };
}
