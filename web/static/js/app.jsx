const { useState, useMemo, useCallback, useEffect } = React;
const {
  ReactFlowProvider,
  ReactFlow: ReactFlowComponent,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
} = window.ReactFlow || {};

const INITIAL_SQL = `CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE orders (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL,
  status VARCHAR(50) DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT NOW(),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE order_items (
  id SERIAL PRIMARY KEY,
  order_id INTEGER NOT NULL REFERENCES orders(id),
  product_id INTEGER NOT NULL,
  quantity INTEGER NOT NULL
);

CREATE VIEW active_orders AS
SELECT o.id, o.user_id, COUNT(oi.id) AS item_count
FROM orders o
LEFT JOIN order_items oi ON o.id = oi.order_id
GROUP BY o.id, o.user_id;`;

const EDGE_COLORS = {
  FK: '#ef4444',
  READ: '#2563eb',
  WRITE: '#16a34a',
  INHERITS: '#8b5cf6',
};

const TYPE_ORDER = ['TABLE', 'MATERIALIZED_VIEW', 'VIEW', 'FUNCTION', 'PROCEDURE'];
const TYPE_LABEL = {
  TABLE: 'Table',
  VIEW: 'View',
  MATERIALIZED_VIEW: 'Materialized View',
  FUNCTION: 'Function',
  PROCEDURE: 'Procedure',
};

function groupByType(objects) {
  return objects.reduce((acc, obj) => {
    const type = obj.type || 'TABLE';
    acc[type] = acc[type] || [];
    acc[type].push(obj);
    return acc;
  }, {});
}

function normalizeKey(value) {
  return value.replace(/\W+/g, '_');
}

function Graph({ data }) {
  const nodes = data.objects || [];
  const edges = data.edges || [];
  const [selectedNodeId, setSelectedNodeId] = useState(null);

  const selectedNodeData = useMemo(() => {
    return selectedNodeId ? nodes.find((n) => n.name === selectedNodeId) : null;
  }, [selectedNodeId, nodes]);

  const elk = useMemo(() => (window.ELK ? new window.ELK() : null), []);
  const [layouting, setLayouting] = useState(false);

  const layout = useMemo(() => {
    const grouped = groupByType(nodes);
    const positions = {};
    let col = 0;
    TYPE_ORDER.forEach((type) => {
      const items = grouped[type] || [];
      items.forEach((obj, index) => {
        positions[obj.name] = {
          x: 240 * col + 40,
          y: 140 * index + 40,
        };
      });
      if (items.length) col += 1;
    });
    return positions;
  }, [nodes]);

  const layoutGraph = useCallback(
    async (nodeList, edgeList) => {
      if (!elk) return nodeList;
      setLayouting(true);
      try {
        const graph = {
          id: 'root',
          layoutOptions: {
            'elk.algorithm': 'layered',
            'elk.direction': 'DOWN',
            'elk.layered.spacing.nodeNode': '40',
            'elk.spacing.nodeNode': '40',
            'elk.layered.spacing.edgeNode': '40',
            'elk.layered.spacing': '40',
          },
          children: nodeList.map((node) => ({
            id: node.id,
            width: 260,
            height: 120,
          })),
          edges: edgeList.map((edge) => ({
            id: edge.id,
            sources: [edge.source],
            targets: [edge.target],
          })),
        };
        const layouted = await elk.layout(graph);
        return nodeList.map((node) => {
          const layoutNode = (layouted.children || []).find((child) => child.id === node.id);
          return layoutNode
            ? {
                ...node,
                position: {
                  x: layoutNode.x || node.position.x,
                  y: layoutNode.y || node.position.y,
                },
              }
            : node;
        });
      } finally {
        setLayouting(false);
      }
    },
    [elk]
  );

  const initialNodes = useMemo(
    () =>
      nodes.map((node) => ({
        id: node.name,
        position: layout[node.name] || { x: 50, y: 50 },
        data: {
          label: (
            <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-soft">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                  {TYPE_LABEL[node.type] || node.type}
                </span>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-medium text-slate-600">
                  {(node.columns && node.columns.length) || 0} cols
                </span>
              </div>
              <h3 className="text-sm font-semibold text-slate-900">{node.name}</h3>
              {node.schema && <p className="mt-2 text-[13px] text-slate-500">Schema: {node.schema}</p>}
            </div>
          ),
        },
        style: {
          width: 260,
          borderRadius: '1rem',
          background: '#ffffff',
          border: '1px solid #e2e8f0',
          boxShadow: '0 12px 40px rgba(15, 23, 42, 0.08)',
        },
      })),
    [nodes, layout]
  );

  const initialEdges = useMemo(
    () =>
      edges.map((edge, index) => ({
        id: `edge-${index}`,
        source: edge.source,
        target: edge.target,
        type: 'smoothstep',
        label: edge.type,
        animated: edge.type === 'FK',
        style: {
          stroke: EDGE_COLORS[edge.type] || '#334155',
        },
        labelBgPadding: [8, 4],
        labelBgBorderRadius: 4,
        labelBgStyle: { fill: '#f8fafc', color: '#334155', fillOpacity: 0.9 },
      })),
    [edges]
  );

  const [reactNodes, setReactNodes, onNodesChange] = useNodesState(initialNodes);
  const [reactEdges, setReactEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    setReactNodes(initialNodes);
    setReactEdges(initialEdges);
  }, [initialNodes, initialEdges]);

  useEffect(() => {
    const autoLayout = async () => {
      if (!elk || !nodes.length) return;
      const layoutedNodes = await layoutGraph(initialNodes, initialEdges);
      setReactNodes(layoutedNodes);
    };

    autoLayout();
  }, [elk, initialEdges, initialNodes, layoutGraph, nodes.length]);

  const onConnect = useCallback(
    (connection) => setReactEdges((eds) => addEdge({ ...connection, animated: true, type: 'smoothstep' }, eds)),
    []
  );

  const onNodeClick = useCallback((event, node) => {
    setSelectedNodeId(node.id);
  }, []);

  return (
    <div className="rounded-3xl border border-slate-200 bg-white shadow-soft p-6">
      <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Lineage Graph</h2>
          <p className="text-sm text-slate-500">Drag nodes to explore dependencies visually.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <button
            type="button"
            onClick={async () => {
              const layoutedNodes = await layoutGraph(reactNodes, reactEdges);
              setReactNodes(layoutedNodes);
            }}
            className="rounded-3xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800"
          >
            {layouting ? 'Aligning...' : 'Auto align'}
          </button>
          <span className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1">FK</span>
          <span className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1">READ</span>
          <span className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1">WRITE</span>
        </div>
      </div>

      <div className="h-[620px] rounded-3xl border border-slate-100 bg-slate-50">
        <ReactFlowProvider>
          <ReactFlowComponent
            nodes={reactNodes}
            edges={reactEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            connectionLineType="smoothstep"
            snapToGrid={true}
            snapGrid={[15, 15]}
          >
            <Background gap={16} color="#e2e8f0" />
            <Controls />
            <MiniMap
              nodeStrokeColor={(node) => {
                if (node.style?.background === '#ffffff') return '#334155';
                return '#999';
              }}
              nodeColor={(node) => {
                return '#ffffff';
              }}
            />
          </ReactFlowComponent>
        </ReactFlowProvider>
      </div>

      {selectedNodeData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
          <div className="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-3xl border border-slate-200 bg-white shadow-2xl">
            <div className="sticky top-0 flex items-center justify-between border-b border-slate-200 bg-slate-50 px-6 py-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                  {TYPE_LABEL[selectedNodeData.type] || selectedNodeData.type}
                </p>
                <h3 className="text-xl font-semibold text-slate-900">{selectedNodeData.name}</h3>
              </div>
              <button
                onClick={() => setSelectedNodeId(null)}
                className="rounded-full p-2 hover:bg-slate-200"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 p-6">
              {selectedNodeData.schema && (
                <div>
                  <p className="text-sm font-semibold text-slate-700">Schema</p>
                  <p className="mt-1 text-sm text-slate-600">{selectedNodeData.schema}</p>
                </div>
              )}

              {selectedNodeData.columns && selectedNodeData.columns.length > 0 && (
                <div>
                  <p className="mb-3 text-sm font-semibold text-slate-700">Columns ({selectedNodeData.columns.length})</p>
                  <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
                    <table className="min-w-full text-sm">
                      <thead className="bg-slate-50">
                        <tr className="border-b border-slate-200">
                          <th className="px-4 py-3 text-left font-semibold text-slate-700">Name</th>
                          <th className="px-4 py-3 text-left font-semibold text-slate-700">Type</th>
                          <th className="px-4 py-3 text-left font-semibold text-slate-700">Nullable</th>
                          <th className="px-4 py-3 text-left font-semibold text-slate-700">Default</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200">
                        {selectedNodeData.columns.map((col, idx) => (
                          <tr key={idx} className="hover:bg-slate-50">
                            <td className="px-4 py-3 font-medium text-slate-900">{col.name || col}</td>
                            <td className="px-4 py-3 text-slate-600">
                              <span className="rounded-full bg-blue-100 px-2 py-1 text-xs font-semibold text-blue-700">
                                {col.type || 'VARCHAR'}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-slate-600">
                              {col.nullable === false ? (
                                <span className="text-xs font-semibold text-red-600">NOT NULL</span>
                              ) : (
                                <span className="text-xs text-slate-500">—</span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-slate-600">
                              {col.default ? (
                                <code className="rounded bg-slate-100 px-2 py-1 text-xs font-mono text-slate-700">
                                  {col.default}
                                </code>
                              ) : (
                                <span className="text-xs text-slate-500">—</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {(!selectedNodeData.columns || selectedNodeData.columns.length === 0) && (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-center">
                  <p className="text-sm text-slate-500">No columns information available</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Stats({ stats }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-soft">
        <p className="text-sm text-slate-500">Objects</p>
        <p className="mt-3 text-3xl font-semibold text-slate-900">{stats.total_objects}</p>
      </div>
      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-soft">
        <p className="text-sm text-slate-500">Edges</p>
        <p className="mt-3 text-3xl font-semibold text-slate-900">{stats.total_edges}</p>
      </div>
      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-soft">
        <p className="text-sm text-slate-500">Cycles</p>
        <p className="mt-3 text-3xl font-semibold text-slate-900">{stats.has_cycles ? 'Detected' : 'None'}</p>
      </div>
      <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-soft">
        <p className="text-sm text-slate-500">Status</p>
        <p className="mt-3 text-3xl font-semibold text-slate-900">{stats.has_cycles ? 'Review' : 'Healthy'}</p>
      </div>
    </div>
  );
}

function EdgeTable({ edges }) {
  if (!edges || edges.length === 0) {
    return <p className="text-sm text-slate-500">No edges found.</p>;
  }
  return (
    <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-soft">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-slate-600">
          <tr>
            <th className="px-4 py-3 text-left font-semibold">Source</th>
            <th className="px-4 py-3 text-left font-semibold">Target</th>
            <th className="px-4 py-3 text-left font-semibold">Type</th>
            <th className="px-4 py-3 text-left font-semibold">Details</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200 bg-white">
          {edges.map((edge, idx) => (
            <tr key={`edge-row-${idx}`} className="hover:bg-slate-50">
              <td className="px-4 py-3 text-slate-700">{edge.source}</td>
              <td className="px-4 py-3 text-slate-700">{edge.target}</td>
              <td className="px-4 py-3">
                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-slate-600">
                  {edge.type}
                </span>
              </td>
              <td className="px-4 py-3 text-slate-600">{edge.details || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Message({ type, message }) {
  if (!message) return null;
  const colors = {
    error: 'bg-rose-50 text-rose-700 border-rose-200',
    success: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  };
  return (
    <div className={`rounded-3xl border p-4 ${colors[type]}`}>
      <p className="text-sm">{message}</p>
    </div>
  );
}

function App() {
  const [ddl, setDdl] = useState(INITIAL_SQL);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [activeTab, setActiveTab] = useState('graph');
  const [selectedExample, setSelectedExample] = useState('basic');

  const examples = {
    basic: INITIAL_SQL,
    cycles: `CREATE TABLE a (id INT PRIMARY KEY);
CREATE TABLE b (id INT PRIMARY KEY, a_id INT REFERENCES a(id));
CREATE VIEW v_a AS SELECT * FROM b WHERE a_id > 0;
CREATE TABLE a_copy AS SELECT * FROM v_a;
ALTER TABLE a ADD FOREIGN KEY (id) REFERENCES a_copy(id);`,
    complex: `CREATE TABLE customers (
  customer_id INT PRIMARY KEY,
  name VARCHAR(100) NOT NULL
);

CREATE TABLE products (
  product_id INT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  price DECIMAL(10,2)
);

CREATE TABLE orders (
  order_id INT PRIMARY KEY,
  customer_id INT NOT NULL,
  order_date DATE,
  FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE order_details (
  order_detail_id INT PRIMARY KEY,
  order_id INT NOT NULL,
  product_id INT NOT NULL,
  quantity INT,
  FOREIGN KEY (order_id) REFERENCES orders(order_id),
  FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE order_summary (
  summary_id INT PRIMARY KEY,
  order_id INT NOT NULL REFERENCES orders(order_id),
  total_amount DECIMAL(10,2)
);

CREATE OR REPLACE PROCEDURE update_order_total(p_order_id INT)
LANGUAGE SQL
AS $$
  UPDATE order_summary
  SET total_amount = (
    SELECT SUM(od.quantity * p.price)
    FROM order_details od
    JOIN products p ON od.product_id = p.product_id
    WHERE od.order_id = p_order_id
  )
  WHERE order_id = p_order_id;
$$;`,
  };

  const handleAnalyze = async () => {
    setError('');
    setSuccess('');
    if (!ddl.trim()) {
      setError('Please enter SQL DDL to analyze.');
      return;
    }
    setLoading(true);
    try {
      const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ddl }),
      });
      const result = await response.json();
      if (!result.success) {
        throw new Error(result.error || 'Analysis failed');
      }
      setData(result.data);
      setActiveTab('graph');
      setSuccess('Analysis completed successfully.');
    } catch (err) {
      setError(err.message || 'Unable to analyze DDL.');
    } finally {
      setLoading(false);
    }
  };

  const handleExample = (name) => {
    setSelectedExample(name);
    setDdl(examples[name]);
    setData(null);
    setError('');
    setSuccess('');
  };

  const handleClear = () => {
    setDdl('');
    setData(null);
    setError('');
    setSuccess('');
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white shadow-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.25em] text-slate-400">DDL Lineage UI</p>
            <h1 className="text-3xl font-semibold text-slate-900">React + Tailwind Lineage Explorer</h1>
          </div>
          <div className="rounded-3xl bg-slate-100 px-4 py-3 text-sm text-slate-600 shadow-sm">
            v2.0 • React • Tailwind
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="grid gap-8 xl:grid-cols-[420px_minmax(0,_1fr)]">
          <section className="space-y-6 rounded-3xl border border-slate-200 bg-white p-6 shadow-soft">
            <div className="space-y-2">
              <h2 className="text-xl font-semibold text-slate-900">SQL DDL Editor</h2>
              <p className="text-sm text-slate-500">Paste your schema statements and analyze lineage graph connections.</p>
            </div>

            <textarea
              value={ddl}
              onChange={(event) => setDdl(event.target.value)}
              rows={16}
              className="w-full resize-none rounded-3xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-900 outline-none transition focus:border-slate-400 focus:ring-4 focus:ring-slate-100"
            />

            <div className="grid gap-3 sm:grid-cols-3">
              <button
                type="button"
                className={`inline-flex items-center justify-center rounded-3xl px-4 py-3 text-sm font-semibold text-white shadow-sm transition ${loading ? 'cursor-not-allowed bg-slate-400' : 'bg-slate-900 hover:bg-slate-700'}`}
                onClick={handleAnalyze}
                disabled={loading}
              >
                {loading ? 'Analyzing...' : 'Analyze'}
              </button>
              <button
                type="button"
                className="rounded-3xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
                onClick={handleClear}
              >
                Clear
              </button>
              <button
                type="button"
                className="rounded-3xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-100"
                onClick={() => downloadJSON(data)}
                disabled={!data}
              >
                Export JSON
              </button>
            </div>

            <div className="space-y-2 rounded-3xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-500">Examples</p>
              <div className="grid gap-2 sm:grid-cols-3">
                {Object.keys(examples).map((name) => (
                  <button
                    key={name}
                    type="button"
                    className={`rounded-3xl px-4 py-3 text-sm font-semibold transition ${selectedExample === name ? 'bg-slate-900 text-white' : 'bg-white text-slate-700 hover:bg-slate-100'}`}
                    onClick={() => handleExample(name)}
                  >
                    {name.charAt(0).toUpperCase() + name.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-4">
              <Message type="error" message={error} />
              <Message type="success" message={success} />
            </div>
          </section>

          <section className="space-y-6">
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-soft">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-slate-900">Analysis Dashboard</h2>
                  <p className="text-sm text-slate-500">View graph, edges, and summary metrics.</p>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className={`rounded-3xl px-4 py-3 text-sm font-semibold transition ${activeTab === 'graph' ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}
                    onClick={() => setActiveTab('graph')}
                  >
                    Graph
                  </button>
                  <button
                    type="button"
                    className={`rounded-3xl px-4 py-3 text-sm font-semibold transition ${activeTab === 'table' ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}
                    onClick={() => setActiveTab('table')}
                  >
                    Edges
                  </button>
                </div>
              </div>

              {data ? (
                <div className="space-y-6">
                  <Stats stats={data.stats} />
                  {activeTab === 'graph' ? <Graph data={data} /> : <EdgeTable edges={data.edges} />}
                </div>
              ) : (
                <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center text-slate-500">
                  Start analysis to render the lineage graph and edge table.
                </div>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  );

  function downloadJSON(content) {
    if (!content) return;
    const dataStr = JSON.stringify(content, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'lineage-analysis.json';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
