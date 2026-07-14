import '@gravity-ui/uikit/styles/fonts.css';
import '@gravity-ui/uikit/styles/styles.css';
import './App.css';

import type {Graph, TBlock, TConnection, TGraphColors} from '@gravity-ui/graph';
import {EAnchorType, ECanDrag, GraphState} from '@gravity-ui/graph';
import {GraphBlock, GraphCanvas, useGraph} from '@gravity-ui/graph/react';
import {ArrowsExpand, ChevronsCollapseUpRight, Moon, Sun} from '@gravity-ui/icons';
import {AsideHeader} from '@gravity-ui/navigation';
import {Button, Icon, Theme, ThemeProvider} from '@gravity-ui/uikit';
import Editor from '@monaco-editor/react';
import React from 'react';
import {format as formatSql} from 'sql-formatter';
import {ProjectSummary, AnalysisResult, LineageGraphBlock, DDLObject, AnalyzeResponse} from './types';


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
    const [isMermaidOpen, setIsMermaidOpen] = React.useState(false);
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

    const formatDdl = () => {
        try {
            setDdl(formatSql(ddl, {language: 'postgresql'}));
            setError('');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unable to format SQL');
        }
    };

    return (
        <ThemeProvider theme={theme}>
            <AsideHeader
                headerDecoration={true}
                compact={compact}
                onChangeCompact={setCompact}
                hideCollapseButton={false}
                logo={{
                    iconSrc: `${process.env.PUBLIC_URL}/ddl-lineage-icon.svg`,
                    text: 'DDL Lineage',
                }}
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
                                    <div className="editor-actions">
                                        <button type="button" onClick={formatDdl} disabled={!ddl.trim()}>
                                            Format SQL
                                        </button>
                                        <button type="button" onClick={analyze} disabled={loading || !ddl.trim()}>
                                            {loading ? 'Analyzing...' : 'Analyze'}
                                        </button>
                                    </div>
                                </div>
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
                                    <LineageGraph result={result} isDark={isDark} />
                                </section>

                                <section className="panel">
                                    <div className="collapsible-header">
                                        <h2>Mermaid Source</h2>
                                        <button
                                            type="button"
                                            aria-expanded={isMermaidOpen}
                                            onClick={() => setIsMermaidOpen((open) => !open)}
                                        >
                                            {isMermaidOpen ? 'Hide' : 'Show'}
                                        </button>
                                    </div>
                                    {isMermaidOpen && <pre>{mermaid || 'graph LR'}</pre>}
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

const LineageGraph = ({result, isDark}: {result: AnalysisResult | null; isDark: boolean}) => {
    const graphContainerRef = React.useRef<HTMLDivElement | null>(null);
    const [isFullscreen, setIsFullscreen] = React.useState(false);
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

    const graphEntities = React.useMemo(() => buildGraphEntities(result, isDark), [isDark, result]);
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

    React.useEffect(() => {
        setEntities(graphEntities);
        fitGraph();
    }, [fitGraph, graphEntities, setEntities]);

    const toggleFullscreen = React.useCallback(async () => {
        if (!graphContainerRef.current) {
            return;
        }

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
                                <div key={`${typedBlock.id}-${field.name}`} className="lineage-node__tooltip-field">
                                    <span>{field.name}</span>
                                    <code>{field.type || 'unknown'}</code>
                                </div>
                            ))
                        ) : (
                            <div className="lineage-node__tooltip-empty">No fields detected</div>
                        )}
                        {hiddenFieldCount > 0 && (
                            <div className="lineage-node__tooltip-more">+{hiddenFieldCount} more fields</div>
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
        return <div className="graph-empty">Run analysis to render the graph.</div>;
    }

    const graphSizeClass = result.stats.total_objects > 80
        ? 'lineage-graph--dense'
        : result.stats.total_objects > 32
            ? 'lineage-graph--large'
            : '';

    return (
        <div ref={graphContainerRef} className={`lineage-graph ${graphSizeClass}`}>
            <div className="lineage-graph__toolbar">
                <span>
                    {result.stats.total_objects} objects · {result.stats.total_edges} edges
                </span>
                <div className="lineage-graph__actions">
                    <button type="button" onClick={fitGraph}>
                        Fit
                    </button>
                    <button
                        type="button"
                        aria-label={isFullscreen ? 'Exit fullscreen' : 'Open graph fullscreen'}
                        title={isFullscreen ? 'Exit fullscreen' : 'Open graph fullscreen'}
                        onClick={toggleFullscreen}
                    >
                        <Icon data={isFullscreen ? ChevronsCollapseUpRight : ArrowsExpand} size={16} />
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

function buildGraphEntities(result: AnalysisResult | null, isDark: boolean): {
    blocks: LineageGraphBlock[];
    connections: TConnection[];
} {
    if (!result) {
        return {blocks: [], connections: []};
    }

    const levelByName = computeLevels(result);
    const objectCount = result.objects.length;
    const blockWidth = objectCount > 80 ? 150 : objectCount > 32 ? 168 : 190;
    const blockHeight = objectCount > 80 ? 76 : objectCount > 32 ? 84 : 96;
    const horizontalGap = objectCount > 80 ? 220 : objectCount > 32 ? 240 : 270;
    const verticalGap = objectCount > 80 ? 104 : objectCount > 32 ? 116 : 138;
    const maxRowsPerLevel = objectCount > 80 ? 10 : objectCount > 32 ? 8 : 12;
    const levelSlots = layoutLevelSlots(result.objects, levelByName, maxRowsPerLevel);

    const blocks = result.objects.map((object) => {
        const slot = levelSlots.get(object.name) || {x: 0, y: 0};
        return {
            id: object.name,
            is: 'lineage-object',
            x: slot.x * horizontalGap,
            y: slot.y * verticalGap,
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
                fields: object.columns.map((column) => ({
                    name: column.name,
                    type: column.type,
                })),
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
            styles: edgeStyles(edge.type, isDark),
        }));

    return {blocks, connections};
}

function layoutLevelSlots(
    objects: DDLObject[],
    levelByName: Map<string, number>,
    maxRowsPerLevel: number,
): Map<string, {x: number; y: number}> {
    const grouped = new Map<number, DDLObject[]>();
    objects.forEach((object) => {
        const level = levelByName.get(object.name) ?? 0;
        grouped.set(level, [...(grouped.get(level) || []), object]);
    });

    const slots = new Map<string, {x: number; y: number}>();
    let xOffset = 0;

    Array.from(grouped.entries())
        .sort(([left], [right]) => left - right)
        .forEach(([, levelObjects]) => {
            const sortedObjects = [...levelObjects].sort((left, right) => {
                if (left.type !== right.type) {
                    return left.type.localeCompare(right.type);
                }
                return left.name.localeCompare(right.name);
            });
            const columnsInLevel = Math.max(1, Math.ceil(sortedObjects.length / maxRowsPerLevel));

            sortedObjects.forEach((object, index) => {
                slots.set(object.name, {
                    x: xOffset + Math.floor(index / maxRowsPerLevel),
                    y: index % maxRowsPerLevel,
                });
            });

            xOffset += columnsInLevel + 1;
        });

    return slots;
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
