import '@gravity-ui/uikit/styles/fonts.css';
import '@gravity-ui/uikit/styles/styles.css';
import './App.css';

import type {
    BlockState,
    Graph,
    LayerPublicProps,
    TBlock,
    TBlockGeometrySnapshot,
    TConnection,
    TGraphColors,
    TGroup,
    TGroupProps,
    UseLayeredLayoutParams,
} from '@gravity-ui/graph';
import {
    BlockGroups,
    EAnchorType,
    ECanDrag,
    GraphState,
    Group,
    useLayeredLayout,
} from '@gravity-ui/graph';
import {GraphBlock, GraphCanvas, useGraph, useLayer} from '@gravity-ui/graph/react';
import {
    ArrowsExpand,
    ChevronLeft,
    ChevronRight,
    ChevronsCollapseUpRight,
    ClockArrowRotateLeft,
    Database,
    Folder,
    Gear,
    Moon,
    Plus,
    Sun,
} from '@gravity-ui/icons';
import {AsideHeader} from '@gravity-ui/navigation';
import {
    Button,
    Icon,
    Theme,
    ThemeProvider,
    Toaster,
    ToasterComponent,
    ToasterProvider,
    useToaster,
} from '@gravity-ui/uikit';
import {ConnectionsPanel} from './ConnectionsPanel';
import {HistoryPanel} from './HistoryPanel';
import {LanguageProvider, useI18n} from './i18n';
import {ProjectsPanel} from './ProjectsPanel';
import {SettingsPanel} from './SettingsPanel';
import Editor from '@monaco-editor/react';
import React from 'react';
import {format as formatSql} from 'sql-formatter';
import {
    AnalysisResult,
    AnalyzeResponse,
    ConnectFormData,
    LineageGraphBlock,
    ProjectSummary,
    SavedConnection,
} from './types';

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
        <LanguageProvider>
            <ThemeProvider theme={theme}>
                <ToasterProvider toaster={toasterInstance}>
                    <AppContent theme={theme} setTheme={setTheme} />
                    <ToasterComponent />
                </ToasterProvider>
            </ThemeProvider>
        </LanguageProvider>
    );
};

const AppContent = ({theme, setTheme}: {theme: Theme; setTheme: (t: Theme) => void}) => {
    const {add: addToast} = useToaster();
    const {t, plural} = useI18n();
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
    const [activePanel, setActivePanel] = React.useState<
        'projects' | 'connections' | 'history' | 'settings' | null
    >(null);
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

    const togglePanel = (panel: 'projects' | 'connections' | 'history' | 'settings') => {
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
                throw new Error(payload.error || t('error.analysisFailed'));
            }
            setResult(payload.data);
            setMermaid(payload.mermaid || '');
            setLastAnalyzedDdl(ddl);
            await loadProjects();
            const {total_objects: totalObjects, total_edges: totalEdges} = payload.data.stats;
            const cycleCount = payload.data.cycles.length;
            const parts = [
                `${totalObjects} ${plural(totalObjects, 'object')}`,
                `${totalEdges} ${plural(totalEdges, 'edge')}`,
            ];
            if (cycleCount > 0) parts.push(`${cycleCount} ${plural(cycleCount, 'cycle')}`);
            addToast({
                name: 'analysis-done',
                theme: cycleCount > 0 ? 'warning' : 'success',
                title: t('toast.analysisTitle'),
                content: parts.join(' · '),
                autoHiding: 4000,
            });
        } catch (err) {
            setError(err instanceof Error ? err.message : t('error.unexpected'));
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
                throw new Error(payload.error || t('error.projectLoadFailed'));
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
                title: t('toast.projectLoadedTitle'),
                content: name,
                autoHiding: 2500,
            });
        } catch (err) {
            setError(err instanceof Error ? err.message : t('error.unexpected'));
        }
    };

    const formatDdl = () => {
        try {
            setDdl(formatSql(ddl, {language: 'postgresql'}));
            setError('');
        } catch (err) {
            setError(err instanceof Error ? err.message : t('error.formatFailed'));
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
                throw new Error(payload.error || t('error.connectionFailed'));
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
                title: t('toast.scanDoneTitle'),
                content: `${t('toast.scanExtracted', {lines: `${lineCount} ${plural(lineCount, 'line')}`})} ${t('toast.scanHint', {analyze: t('editor.analyze')})}`,
                autoHiding: 5000,
            });
        } catch (err) {
            const msg = err instanceof Error ? err.message : t('error.connectionFailed');
            setScanError(msg);
            addToast({
                name: 'scan-error',
                theme: 'danger',
                title: t('toast.scanFailedTitle'),
                content: msg,
                autoHiding: 5000,
            });
        } finally {
            setScanning(false);
        }
    };

    const handleRestoreVersion = async (name: string, id: number) => {
        setError('');
        try {
            const response = await fetch(`/api/project/${encodeURIComponent(name)}/history/${id}`);
            const payload = await response.json();
            if (!response.ok || !payload.success) {
                throw new Error(payload.error || t('error.restoreFailed'));
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
                title: t('toast.versionRestoredTitle'),
                autoHiding: 2500,
            });
        } catch (err) {
            addToast({
                name: 'restore-error',
                theme: 'danger',
                title: t('toast.restoreFailedTitle'),
                content: err instanceof Error ? err.message : undefined,
                autoHiding: 3000,
            });
        }
    };

    const handleDeleteProject = async (name: string) => {
        try {
            const response = await fetch(`/api/project/${encodeURIComponent(name)}`, {
                method: 'DELETE',
            });
            const payload = await response.json();
            if (!response.ok || !payload.success)
                throw new Error(payload.error || t('error.deleteFailed'));
            setProjects(payload.projects || []);
            addToast({
                name: 'project-deleted',
                theme: 'normal',
                title: t('toast.projectDeletedTitle', {name}),
                autoHiding: 2500,
            });
        } catch {
            addToast({
                name: 'delete-error',
                theme: 'danger',
                title: t('toast.deleteFailedTitle'),
                autoHiding: 3000,
            });
        }
    };

    const copyText = async (text: string, label: string) => {
        try {
            await navigator.clipboard.writeText(text);
            addToast({
                name: `copy-${label}`,
                theme: 'success',
                title: t('toast.copiedTitle', {label}),
                autoHiding: 2000,
            });
        } catch {
            addToast({
                name: 'copy-error',
                theme: 'danger',
                title: t('toast.copyFailedTitle'),
                autoHiding: 2000,
            });
        }
    };

    // Ctrl/Cmd+Enter must call the current analyze(): it also reads the language,
    // toasts and project state, not only the DDL
    const analyzeRef = React.useRef(analyze);
    analyzeRef.current = analyze;
    React.useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                analyzeRef.current();
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, []);

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
                    title: t('menu.projects'),
                    icon: Folder,
                    current: activePanel === 'projects',
                    onItemClick: () => togglePanel('projects'),
                },
                {
                    id: 'connections',
                    title: t('menu.connections'),
                    icon: Database,
                    current: activePanel === 'connections',
                    onItemClick: () => togglePanel('connections'),
                },
                {
                    id: 'history',
                    title: t('menu.history'),
                    icon: ClockArrowRotateLeft,
                    current: activePanel === 'history',
                    onItemClick: () => togglePanel('history'),
                },
                {
                    id: 'settings',
                    title: t('menu.settings'),
                    icon: Gear,
                    current: activePanel === 'settings',
                    onItemClick: () => togglePanel('settings'),
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
                                loadProject(name);
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
                {
                    id: 'settings',
                    visible: activePanel === 'settings',
                    children: <SettingsPanel />,
                },
            ]}
            onClosePanel={() => setActivePanel(null)}
            renderFooter={() => (
                <div className="sidebar-footer">
                    <Button
                        size="l"
                        view="flat"
                        title={isDark ? t('theme.toLight') : t('theme.toDark')}
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

                    <section
                        className={`workspace${editorCollapsed ? ' workspace--collapsed' : ''}`}
                    >
                        <div
                            className={`editor-pane${editorCollapsed ? ' editor-pane--collapsed' : ''}`}
                        >
                            <div className="pane-header">
                                <h2>{t('editor.title')}</h2>
                                <div className="editor-actions">
                                    {!editorCollapsed && (
                                        <>
                                            <button
                                                type="button"
                                                className="btn-secondary btn-icon"
                                                title={t('editor.newTitle')}
                                                onClick={clearAll}
                                            >
                                                <Icon data={Plus} size={14} />
                                                {t('editor.new')}
                                            </button>
                                            <button
                                                type="button"
                                                className="btn-secondary"
                                                onClick={formatDdl}
                                                disabled={!ddl.trim()}
                                            >
                                                {t('editor.formatSql')}
                                            </button>
                                            <button
                                                type="button"
                                                className={hasChanges ? undefined : 'btn-secondary'}
                                                title="Ctrl+Enter"
                                                onClick={() => analyze()}
                                                disabled={loading || !ddl.trim()}
                                            >
                                                {loading
                                                    ? t('editor.analyzing')
                                                    : t('editor.analyze')}
                                            </button>
                                        </>
                                    )}
                                    <button
                                        type="button"
                                        className="btn-secondary btn-collapse"
                                        title={
                                            editorCollapsed
                                                ? t('editor.expand')
                                                : t('editor.collapse')
                                        }
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
                                                fontFamily:
                                                    "'IBM Plex Mono', SFMono-Regular, Consolas, monospace",
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
                            <section className="panel">
                                <h2>{t('results.graph')}</h2>
                                <LineageGraph result={result} isDark={isDark} />
                            </section>

                            <section className="panel panel--merged">
                                <div className="panel__block">
                                    <h2>
                                        {t('results.objects')}
                                        {result && (
                                            <span className="panel-count">
                                                {result.objects.length}
                                            </span>
                                        )}
                                    </h2>
                                    <div className="table-wrap">
                                        <table>
                                            <thead>
                                                <tr>
                                                    <th>{t('table.name')}</th>
                                                    <th>{t('table.type')}</th>
                                                    <th>{t('table.columns')}</th>
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
                                                                <span className="temp-badge">
                                                                    {t('node.temp')}
                                                                </span>
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
                                                {!result && (
                                                    <EmptyRow colSpan={3} text={t('table.empty')} />
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>

                                <div className="panel__hr" />

                                <div className="panel__block">
                                    <h2>
                                        {t('results.relationships')}
                                        {result && (
                                            <span className="panel-count">
                                                {result.edges.length}
                                            </span>
                                        )}
                                    </h2>
                                    <div className="table-wrap">
                                        <table>
                                            <thead>
                                                <tr>
                                                    <th>{t('table.source')}</th>
                                                    <th>{t('table.type')}</th>
                                                    <th>{t('table.target')}</th>
                                                    <th>{t('table.details')}</th>
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
                                                {!result && (
                                                    <EmptyRow colSpan={4} text={t('table.empty')} />
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>

                                <div className="panel__hr" />

                                <div className="panel__block">
                                    <h2>{t('results.executionOrder')}</h2>
                                    <div className="exec-order">
                                        {result?.topo_order?.length ? (
                                            result.topo_order.map((name, i) => (
                                                <React.Fragment key={name + i}>
                                                    {i > 0 && (
                                                        <span className="exec-order__sep">→</span>
                                                    )}
                                                    <span className="exec-order__step">{name}</span>
                                                </React.Fragment>
                                            ))
                                        ) : (
                                            <span className="exec-order__empty">
                                                {t('execOrder.empty')}
                                            </span>
                                        )}
                                    </div>
                                </div>

                                <div className="panel__hr" />

                                <div className="panel__block">
                                    <div className="collapsible-header">
                                        <h2>{t('results.export')}</h2>
                                        <div className="export-actions">
                                            <button
                                                type="button"
                                                className="btn-secondary"
                                                disabled={!mermaid}
                                                onClick={() => copyText(mermaid, 'Mermaid')}
                                            >
                                                {t('export.copyMermaid')}
                                            </button>
                                            <button
                                                type="button"
                                                className="btn-secondary"
                                                disabled={!result}
                                                onClick={() =>
                                                    copyText(
                                                        JSON.stringify(result, null, 2),
                                                        'JSON',
                                                    )
                                                }
                                            >
                                                {t('export.copyJson')}
                                            </button>
                                            <button
                                                type="button"
                                                className="btn-secondary"
                                                aria-expanded={isMermaidOpen}
                                                onClick={() => setIsMermaidOpen((open) => !open)}
                                            >
                                                {isMermaidOpen
                                                    ? t('export.hidePreview')
                                                    : t('export.preview')}
                                            </button>
                                        </div>
                                    </div>
                                    {isMermaidOpen && <pre>{mermaid || 'graph LR'}</pre>}
                                </div>
                            </section>
                        </div>
                    </section>
                </main>
            )}
        />
    );
};

const EmptyRow = ({colSpan, text}: {colSpan: number; text: string}) => (
    <tr>
        <td colSpan={colSpan} className="empty">
            {text}
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
    const {t, plural} = useI18n();
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

    useLayer(graph, FunctionGroupsLayer, FUNCTION_GROUPS_LAYER_PROPS);

    // Block dimensions depend on object count
    const blockDims = React.useMemo(() => {
        const count = result?.objects.length ?? 0;
        return {
            width: count > 80 ? 150 : count > 32 ? 168 : 190,
            height: count > 80 ? 76 : count > 32 ? 84 : 96,
        };
    }, [result]);

    // Functions/procedures as groups + data-flow links
    const view = React.useMemo(
        () => (result ? buildLineageView(result, blockDims) : null),
        [result, blockDims],
    );

    // Input for the built-in layered layout algorithm. Each function group is
    // collapsed into one super-node so that groups never overlap other blocks.
    const layoutInput = React.useMemo((): UseLayeredLayoutParams => {
        if (!result || !view) return {blocks: [], connections: []};
        const count = result.objects.length;
        const layoutNodeId = (name: string) => {
            const owner = view.groupOf.get(name);
            return owner ? groupLayoutId(owner) : name;
        };

        const blocks: UseLayeredLayoutParams['blocks'] = [];
        view.groups.forEach((group) => {
            blocks.push({id: groupLayoutId(group.owner), width: group.width, height: group.height});
        });
        view.nodes
            .filter((name) => !view.groupOf.has(name))
            .forEach((name) =>
                blocks.push({id: name, width: blockDims.width, height: blockDims.height}),
            );

        const seen = new Set<string>();
        const connections: UseLayeredLayoutParams['connections'] = [];
        view.links.forEach((l) => {
            const source = layoutNodeId(l.from);
            const target = layoutNodeId(l.to);
            const key = `${source}->${target}`;
            if (source === target || seen.has(key)) return;
            seen.add(key);
            connections.push({
                id: `layout-${connections.length}`,
                sourceBlockId: source,
                targetBlockId: target,
            });
        });

        // The built-in level assignment drops every node on a cycle to level 0
        // (e.g. a function reading and updating the same table), so pass our own
        const levels = computeLayerLevels(
            blocks.map((b) => String(b.id)),
            connections,
        );
        for (const block of blocks) {
            block.level = levels.get(String(block.id));
        }

        return {
            blocks,
            connections,
            layoutOptions: {
                nodeHorizontalGap: count > 80 ? 48 : count > 32 ? 64 : 80,
                nodeVerticalGap: count > 80 ? 100 : count > 32 ? 116 : 136,
            },
        };
    }, [result, view, blockDims]);

    const {result: rawLayoutResult, isLoading: layoutLoading} = useLayeredLayout(layoutInput);

    // The layered layout uses a fixed layer step, so wide/tall group nodes would
    // overlap their neighbours. Re-space layers and nodes using real sizes.
    const layoutResult = React.useMemo(
        () =>
            rawLayoutResult && {
                ...rawLayoutResult,
                blocks: packLayers(rawLayoutResult.blocks, layoutInput.blocks),
            },
        [rawLayoutResult, layoutInput.blocks],
    );

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
        if (!result || !view)
            return {blocks: [] as LineageGraphBlock[], connections: [] as TConnection[]};

        const store = userPositionsRef.current;
        const savedPos =
            store.forResult === result ? store.map : new Map<string, {x: number; y: number}>();
        const visible = new Set(view.nodes);

        const blocks: LineageGraphBlock[] = result.objects
            .filter((o) => visible.has(o.name))
            .map((object) => {
                const owner = view.groupOf.get(object.name);
                let layoutPos = layoutResult?.blocks?.[object.name];
                if (owner) {
                    const group = view.groups.get(owner)!;
                    const groupPos = layoutResult?.blocks?.[groupLayoutId(owner)];
                    const offset = group.offsets.get(object.name)!;
                    layoutPos = groupPos && {x: groupPos.x + offset.x, y: groupPos.y + offset.y};
                }
                const pos = savedPos.get(object.name) ?? layoutPos ?? {x: 0, y: 0};
                return {
                    id: object.name,
                    is: 'lineage-object',
                    group: owner,
                    x: pos.x,
                    y: pos.y,
                    width: blockDims.width,
                    height: blockDims.height,
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
                        fields: object.columns.map((c) => ({name: c.name, type: c.type})),
                        temporary: Boolean(object.temporary),
                    },
                };
            });

        const connections: TConnection[] = view.links
            .filter((l) => visible.has(l.from) && visible.has(l.to))
            .map((l, i) => ({
                id: `${l.type}-${l.from}-${l.to}-${i}`,
                sourceBlockId: l.from,
                sourceAnchorId: `${l.from}-out`,
                targetBlockId: l.to,
                targetAnchorId: `${l.to}-in`,
                label: linkLabel(l, view.groupOf),
                styles: edgeStyles(l.type),
            }));

        return {blocks, connections};
    }, [result, view, layoutResult, blockDims]);

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

    const renderBlock = React.useCallback(
        (currentGraph: Graph, block: TBlock) => {
            const typedBlock = block as LineageGraphBlock;
            const meta = typedBlock.meta;
            const displayName = meta?.schema
                ? `${meta.schema}.${typedBlock.name}`
                : typedBlock.name;
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
                                <div className="lineage-node__tooltip-empty">
                                    {t('node.noFields')}
                                </div>
                            )}
                            {hiddenFieldCount > 0 && (
                                <div className="lineage-node__tooltip-more">
                                    +
                                    {t('node.moreFields', {
                                        count: hiddenFieldCount,
                                        word: plural(hiddenFieldCount, 'field'),
                                    })}
                                </div>
                            )}
                        </div>
                    </div>
                    <div className={`lineage-node__type type-${meta?.objectType.toLowerCase()}`}>
                        {objectType}
                    </div>
                    {meta?.temporary && <div className="lineage-node__temp">{t('node.temp')}</div>}
                    <div className="lineage-node__name">{typedBlock.name}</div>
                    <div className="lineage-node__meta">
                        {meta?.schema ? `${meta.schema} · ` : ''}
                        {meta?.columns ?? 0} {plural(meta?.columns ?? 0, 'column')}
                    </div>
                </GraphBlock>
            );
        },
        [t, plural],
    );

    if (!result) {
        const [hintBefore, hintAfter] = t('graph.emptyHint').split('{analyze}');
        return (
            <div className="graph-empty">
                <div className="graph-empty__hint">
                    {hintBefore}
                    <strong>{t('editor.analyze')}</strong>
                    {hintAfter}
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

    const cycleCount = result.cycles.length;

    return (
        <div ref={graphContainerRef} className={`lineage-graph ${graphSizeClass}`}>
            <div className="lineage-graph__toolbar">
                <div className="lineage-titleblock">
                    <span
                        className={`lineage-titleblock__text${cycleCount > 0 ? ' lineage-titleblock__text--warn' : ''}`}
                    >
                        {t('graph.titleObj')} {result.stats.total_objects} · {t('graph.titleEdge')}{' '}
                        {result.stats.total_edges} · {t('graph.titleCycles')} {cycleCount}
                    </span>
                </div>
                <div className="lineage-legend">
                    {EDGE_LEGEND.map(({type, cls}) => (
                        <span key={type} className={`edge ${cls}`}>
                            {type}
                        </span>
                    ))}
                </div>
                <div className="lineage-graph__actions">
                    <button type="button" onClick={fitGraph}>
                        {t('graph.fit')}
                    </button>
                    <button
                        type="button"
                        aria-label={
                            isFullscreen ? t('graph.fullscreenClose') : t('graph.fullscreenOpen')
                        }
                        title={
                            isFullscreen ? t('graph.fullscreenClose') : t('graph.fullscreenOpen')
                        }
                        onClick={() => toggleFullscreen()}
                    >
                        <Icon
                            data={isFullscreen ? ChevronsCollapseUpRight : ArrowsExpand}
                            size={16}
                        />
                    </button>
                </div>
            </div>
            <div className="lineage-graph__canvas-wrap">
                <span className="reg-mark reg-mark--tl">+</span>
                <span className="reg-mark reg-mark--tr">+</span>
                <span className="reg-mark reg-mark--bl">+</span>
                <span className="reg-mark reg-mark--br">+</span>
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
        </div>
    );
};

const GROUP_OWNER_TYPES = new Set(['FUNCTION', 'PROCEDURE']);
const GROUP_PADDING = {top: 44, right: 24, bottom: 24, left: 24};
const GROUP_INNER_GAP = {x: 72, y: 24};

type FunctionGroupLayout = {
    owner: string;
    /** Blocks drawn inside the group: tables it creates (+ the function block when linked) */
    members: string[];
    /** Block offsets relative to the group's layout node (top-left incl. padding) */
    offsets: Map<string, {x: number; y: number}>;
    width: number;
    height: number;
};

/** Data-flow link: `from` is where the data comes from */
type LineageLink = {from: string; to: string; type: string; details: string; via?: string};

type LineageView = {
    /** Objects rendered as blocks */
    nodes: string[];
    links: LineageLink[];
    groups: Map<string, FunctionGroupLayout>;
    /** Block name -> owning function group */
    groupOf: Map<string, string>;
};

type TFunctionGroup = TGroup & {title: string};

const groupLayoutId = (owner: string) => `group:${owner}`;

const PACK_GAP = {x: 96, y: 40};

/** Longest-path levels on the graph with DFS back edges (cycles) ignored */
function computeLayerLevels(
    ids: string[],
    connections: UseLayeredLayoutParams['connections'],
): Map<string, number> {
    const out = new Map(ids.map((id) => [id, [] as string[]]));
    connections.forEach((c) => out.get(String(c.sourceBlockId))?.push(String(c.targetBlockId)));

    // DFS post-order gives a topological order of the graph without back edges
    const state = new Map<string, 'active' | 'done'>();
    const dagOut = new Map(ids.map((id) => [id, [] as string[]]));
    const order: string[] = [];
    const visit = (id: string) => {
        state.set(id, 'active');
        out.get(id)!.forEach((next) => {
            if (!out.has(next) || state.get(next) === 'active') return;
            dagOut.get(id)!.push(next);
            if (!state.has(next)) visit(next);
        });
        state.set(id, 'done');
        order.push(id);
    };
    ids.forEach((id) => !state.has(id) && visit(id));

    const level = new Map(ids.map((id) => [id, 0]));
    order.reverse().forEach((id) => {
        dagOut
            .get(id)!
            .forEach((next) => level.set(next, Math.max(level.get(next)!, level.get(id)! + 1)));
    });
    return level;
}

/** Shift layers (same x) and nodes inside each layer so that no two nodes overlap */
function packLayers(
    positions: Record<string, {x: number; y: number}>,
    nodes: UseLayeredLayoutParams['blocks'],
): Record<string, {x: number; y: number}> {
    const sizes = new Map(
        nodes.map((n) => [String(n.id), {width: n.width ?? 0, height: n.height ?? 0}]),
    );
    const layers = new Map<number, string[]>();
    Object.entries(positions).forEach(([id, pos]) => {
        if (!sizes.has(id)) return;
        const key = Math.round(pos.x);
        if (!layers.has(key)) layers.set(key, []);
        layers.get(key)!.push(id);
    });

    const packed: Record<string, {x: number; y: number}> = {...positions};
    let shiftX = 0;
    let cursorX = -Infinity;
    [...layers.keys()]
        .sort((a, b) => a - b)
        .forEach((layerX) => {
            const ids = layers.get(layerX)!.sort((a, b) => positions[a].y - positions[b].y);
            const x = Math.max(layerX + shiftX, cursorX);
            shiftX = x - layerX;
            cursorX = x + Math.max(...ids.map((id) => sizes.get(id)!.width)) + PACK_GAP.x;

            let cursorY = -Infinity;
            ids.forEach((id) => {
                const y = Math.max(positions[id].y, cursorY);
                packed[id] = {x, y};
                cursorY = y + sizes.get(id)!.height + PACK_GAP.y;
            });
        });
    return packed;
}

/**
 * Turn the analysis result into what the graph draws.
 *
 * Every function/procedure is a group. Tables created inside its body
 * (`parent`) are drawn in the group; everything it only reads or writes stays
 * outside. Links come from statement-level `flows`, so data goes table → table
 * (also across groups). The function block itself is shown only when a flow
 * starts or ends at the function (a write with no source, a read with no
 * target) or the group would otherwise be empty.
 */
function buildLineageView(
    result: AnalysisResult,
    blockDims: {width: number; height: number},
): LineageView {
    const names = new Set(result.objects.map((o) => o.name));
    const owners = new Set(
        result.objects
            .filter((o) => GROUP_OWNER_TYPES.has(o.type.toUpperCase()))
            .map((o) => o.name),
    );

    const links: LineageLink[] = [];
    const seen = new Set<string>();
    const addLink = (link: LineageLink) => {
        const key = `${link.from}|${link.to}|${link.type}|${link.details}`;
        if (link.from === link.to || seen.has(key) || !names.has(link.from) || !names.has(link.to))
            return;
        seen.add(key);
        links.push(link);
    };

    // Function-level READ/WRITE edges are replaced by statement-level flows.
    // Older saved results have no flows: fall back to the edges, oriented as data flow.
    const hasFlows = Array.isArray(result.flows);
    result.edges.forEach((e) => {
        const fromFunction = owners.has(e.source) && (e.type === 'READ' || e.type === 'WRITE');
        if (fromFunction && hasFlows) return;
        if (fromFunction && e.type === 'WRITE') {
            addLink({from: e.source, to: e.target, type: e.type, details: e.details});
        } else {
            // edge.source depends on edge.target, so data flows target -> source
            addLink({from: e.target, to: e.source, type: e.type, details: e.details});
        }
    });
    result.flows?.forEach((f) =>
        addLink({from: f.source, to: f.target, type: f.type, details: f.details, via: f.via}),
    );

    const membersByOwner = new Map<string, string[]>([...owners].map((owner) => [owner, []]));
    result.objects.forEach((o) => {
        if (o.parent && owners.has(o.parent)) membersByOwner.get(o.parent)!.push(o.name);
    });

    const linked = new Set(links.flatMap((l) => [l.from, l.to]));
    const groups = new Map<string, FunctionGroupLayout>();
    const groupOf = new Map<string, string>();
    membersByOwner.forEach((tables, owner) => {
        const members = linked.has(owner) || !tables.length ? [...tables, owner] : tables;
        const layout = layoutGroup(owner, members, links, blockDims);
        groups.set(owner, layout);
        members.forEach((member) => groupOf.set(member, owner));
    });

    const nodes = result.objects
        .map((o) => o.name)
        .filter((name) => !owners.has(name) || groups.get(name)!.members.includes(name));
    return {nodes, links, groups, groupOf};
}

/** Name the function when a flow it performs runs entirely outside its group */
function linkLabel(link: LineageLink, groupOf: Map<string, string>): string {
    const label = link.details ? `${link.type} ${link.details}` : link.type;
    const outsideGroup =
        link.via && groupOf.get(link.from) !== link.via && groupOf.get(link.to) !== link.via;
    return outsideGroup ? `${label} · ƒ ${link.via}` : label;
}

/** Arrange group members in columns by data-flow depth inside the group */
function layoutGroup(
    owner: string,
    members: string[],
    links: LineageLink[],
    blockDims: {width: number; height: number},
): FunctionGroupLayout {
    const inside = new Set(members);
    const internal = links.filter((l) => inside.has(l.from) && inside.has(l.to));
    const level = new Map(members.map((m) => [m, 0]));
    // Longest-path levels; bounded passes keep cycles from looping forever
    for (let pass = 0; pass < members.length; pass++) {
        let changed = false;
        internal.forEach((l) => {
            const next = level.get(l.from)! + 1;
            if (next > level.get(l.to)! && next < members.length) {
                level.set(l.to, next);
                changed = true;
            }
        });
        if (!changed) break;
    }

    const columns: string[][] = [];
    members.forEach((m) => {
        const column = level.get(m)!;
        columns[column] = [...(columns[column] ?? []), m];
    });
    const filled = columns.filter(Boolean);
    const rowStep = blockDims.height + GROUP_INNER_GAP.y;
    const colStep = blockDims.width + GROUP_INNER_GAP.x;
    const maxRows = Math.max(...filled.map((col) => col.length));
    const contentHeight = maxRows * rowStep - GROUP_INNER_GAP.y;

    const offsets = new Map<string, {x: number; y: number}>();
    filled.forEach((col, ci) => {
        const top = (contentHeight - (col.length * rowStep - GROUP_INNER_GAP.y)) / 2;
        col.forEach((m, ri) => {
            offsets.set(m, {
                x: GROUP_PADDING.left + ci * colStep,
                y: GROUP_PADDING.top + top + ri * rowStep,
            });
        });
    });

    return {
        owner,
        members,
        offsets,
        width:
            GROUP_PADDING.left + filled.length * colStep - GROUP_INNER_GAP.x + GROUP_PADDING.right,
        height: GROUP_PADDING.top + contentHeight + GROUP_PADDING.bottom,
    };
}

class FunctionGroup extends Group<TFunctionGroup> {
    // Group.define() subclasses the base Group, so styles are injected here instead
    constructor(props: TGroupProps, parent: BlockGroups) {
        super(
            {
                ...props,
                style: {
                    background: 'rgba(232, 163, 61, 0.07)',
                    border: 'rgba(232, 163, 61, 0.55)',
                    borderWidth: 1.5,
                    selectedBackground: 'rgba(232, 163, 61, 0.14)',
                    selectedBorder: '#ffc978',
                    ...props.style,
                },
                geometry: {
                    padding: [
                        GROUP_PADDING.top,
                        GROUP_PADDING.right,
                        GROUP_PADDING.bottom,
                        GROUP_PADDING.left,
                    ],
                    ...props.geometry,
                },
            },
            parent,
        );
    }

    protected override render() {
        super.render();
        const ctx = this.context.ctx;
        const rect = this.getRect();
        ctx.save();
        ctx.fillStyle = '#e8a33d';
        ctx.font = '600 14px "JetBrains Mono", ui-monospace, monospace';
        ctx.textBaseline = 'top';
        ctx.fillText(`ƒ ${this.state.title}`, rect.x + 16, rect.y + 14, rect.width - 32);
        ctx.restore();
    }
}

const FunctionGroupsLayer = BlockGroups.withBlockGrouping({
    groupingFn: (blocks: BlockState[]) => {
        const byGroup: Record<string, BlockState[]> = {};
        blocks.forEach((block) => {
            const group = block.asTBlock().group;
            if (!group) return;
            (byGroup[group] ??= []).push(block);
        });
        return byGroup;
    },
    mapToGroups: (key, {rect}): TFunctionGroup => ({
        id: key,
        title: key,
        rect,
        component: FunctionGroup as typeof Group,
    }),
});

// LayerPublicProps can't infer props through withBlockGrouping's return type
const FUNCTION_GROUPS_LAYER_PROPS = {
    draggable: true,
    updateBlocksOnDrag: true,
} as LayerPublicProps<typeof FunctionGroupsLayer>;

function edgeStyles(type: string): TConnection['styles'] {
    if (type === 'WRITE') {
        return {background: '#e8a33d', selectedBackground: '#ffc978'};
    }
    if (type === 'READ') {
        return {background: '#7db8ff', selectedBackground: '#aed4ff'};
    }
    if (type === 'INHERITS') {
        return {background: '#5cd9a0', selectedBackground: '#8ce8bc', dashes: [8, 6]};
    }
    return {background: '#6fe0e0', selectedBackground: '#a8f0f0', dashes: [6, 5]};
}

// The graph canvas is a fixed cyanotype "instrument" — it keeps the same
// blueprint palette regardless of the app's light/dark theme.
function graphThemeColors(isDark: boolean): TGraphColors {
    return {
        canvas: {
            belowLayerBackground: '#0e2a52',
            layerBackground: '#0e2a52',
            dots: 'rgba(111, 224, 224, 0.18)',
            border: isDark ? '#2c4a78' : '#0b2242',
        },
        block: {
            background: '#f5f6f2',
            border: 'rgba(16, 24, 43, 0.16)',
            text: '#10182b',
            selectedBorder: '#6fe0e0',
        },
        anchor: {
            background: '#6fe0e0',
            selectedBorder: '#6fe0e0',
        },
        connection: {
            background: '#6fe0e0',
            selectedBackground: '#bff5f5',
        },
        connectionLabel: {
            background: '#0e2a52',
            hoverBackground: '#123a6e',
            selectedBackground: '#123a6e',
            text: '#cfe7ff',
            hoverText: '#ffffff',
            selectedText: '#ffffff',
        },
        selection: {
            background: 'rgba(111, 224, 224, 0.14)',
            border: '#6fe0e0',
        },
    };
}
