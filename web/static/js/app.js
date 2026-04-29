/**
 * DDL Lineage Web Interface - Client Side
 */

let currentAnalysisResult = null;

// Initialize on document load
document.addEventListener('DOMContentLoaded', function() {
    // Event listeners
    document.getElementById('analyzeBtn').addEventListener('click', analyzeSQL);
    document.getElementById('clearBtn').addEventListener('click', clearAll);
    document.getElementById('downloadBtn').addEventListener('click', downloadResults);
    
    // Load example SQL on page load
    loadExample('basic');
    
    // Initialize Mermaid
    mermaid.initialize({ startOnLoad: true, theme: 'default' });
});

/**
 * Analyze the SQL DDL input
 */
async function analyzeSQL() {
    const ddlText = document.getElementById('ddlInput').value.trim();
    
    if (!ddlText) {
        showError('Please enter SQL DDL content');
        return;
    }
    
    const analyzeBtn = document.getElementById('analyzeBtn');
    analyzeBtn.classList.add('loading');
    analyzeBtn.disabled = true;
    
    try {
        // Call API
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ ddl: ddlText })
        });
        
        const result = await response.json();
        
        if (!result.success) {
            showError(result.error);
            return;
        }
        
        currentAnalysisResult = result;
        
        // Update UI with results
        updateStats(result.data.stats);
        updateObjects(result.data.objects);
        updateCycles(result.data.cycles);
        updateMermaidDiagram(result.mermaid);
        updateEdgesTable(result.data.edges);
        updateTopoOrder();
        
        // Enable download button
        document.getElementById('downloadBtn').disabled = false;
        
        showSuccess(`Analysis complete! Found ${result.data.stats.total_objects} objects and ${result.data.stats.total_edges} edges.`);
        
    } catch (error) {
        showError('Failed to analyze SQL: ' + error.message);
    } finally {
        analyzeBtn.classList.remove('loading');
        analyzeBtn.disabled = false;
    }
}

/**
 * Get topological sort order
 */
async function updateTopoOrder() {
    if (!currentAnalysisResult) return;
    
    const ddlText = document.getElementById('ddlInput').value.trim();
    
    try {
        const response = await fetch('/api/topo', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ ddl: ddlText })
        });
        
        const result = await response.json();
        
        if (result.success && result.order) {
            const html = result.order.length > 0
                ? `<ol>${result.order.map(o => `<li><code>${o}</code></li>`).join('')}</ol>`
                : '<p class="has-text-grey">No topological order available</p>';
            
            document.getElementById('topoContent').innerHTML = html;
        }
    } catch (error) {
        console.error('Error getting topo order:', error);
    }
}

/**
 * Update statistics panel
 */
function updateStats(stats) {
    const html = `
        <div class="columns is-multiline">
            <div class="column is-half">
                <div class="box" style="border-left: 4px solid #3273dc;">
                    <p class="heading">Objects</p>
                    <p class="title">${stats.total_objects}</p>
                </div>
            </div>
            <div class="column is-half">
                <div class="box" style="border-left: 4px solid #48c774;">
                    <p class="heading">Edges</p>
                    <p class="title">${stats.total_edges}</p>
                </div>
            </div>
            <div class="column is-half">
                <div class="box" style="border-left: 4px solid #209cee;">
                    <p class="heading">Cycles</p>
                    <p class="title">${stats.has_cycles ? '⚠️ Found' : '✓ None'}</p>
                </div>
            </div>
            <div class="column is-half">
                <div class="box" style="border-left: 4px solid #ffdd57;">
                    <p class="heading">Status</p>
                    <p class="title">${stats.has_cycles ? 'Invalid' : 'Valid'}</p>
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('statsContent').innerHTML = html;
}

/**
 * Update objects list
 */
function updateObjects(objects) {
    if (objects.length === 0) {
        document.getElementById('objectsContent').innerHTML = '<p class="has-text-grey">No objects found</p>';
        return;
    }
    
    let html = '';
    
    for (const obj of objects) {
        const typeClass = obj.type.toLowerCase();
        const icon = {
            'TABLE': '📊',
            'VIEW': '👁️',
            'MATERIALIZED_VIEW': '💾',
            'FUNCTION': '⚙️',
            'PROCEDURE': '▶️'
        }[obj.type] || '📦';
        
        const cols = obj.columns.length > 0
            ? `<div class="columns-list">
                 <strong>Columns (${obj.columns.length}):</strong>
                 <ul style="margin: 0.25rem 0 0 1rem; font-size: 0.8rem;">
                   ${obj.columns.map(c => `
                     <li><code>${c.name}</code> ${c.pk ? '<span class="badge">PK</span>' : ''} ${c.fk ? '<span class="badge">FK</span>' : ''}</li>
                   `).join('')}
                 </ul>
               </div>`
            : '';
        
        html += `
            <div class="object-card ${typeClass}">
                <div class="object-name">${icon} ${obj.name}</div>
                <div class="object-type">${obj.type}${obj.schema ? ` • ${obj.schema}` : ''}</div>
                ${cols}
            </div>
        `;
    }
    
    document.getElementById('objectsContent').innerHTML = html;
}

/**
 * Update cycles information
 */
function updateCycles(cycles) {
    if (!cycles || cycles.length === 0) {
        document.getElementById('cyclesContent').innerHTML = 
            '<p class="success-message">✓ No cycles detected - schema is valid</p>';
        return;
    }
    
    let html = '<div style="background-color: #fff3cd; padding: 1rem; border-radius: 4px; border-left: 3px solid #ff9800;">';
    html += `<strong style="color: #ff6f00;">⚠️ Found ${cycles.length} cycle(s)</strong><ul>`;
    
    for (const cycle of cycles) {
        const path = cycle.join(' → ');
        html += `<li style="margin: 0.5rem 0; font-family: monospace; font-size: 0.85rem;">${path}</li>`;
    }
    
    html += '</ul></div>';
    
    document.getElementById('cyclesContent').innerHTML = html;
}

/**
 * Update Mermaid diagram
 */
function updateMermaidDiagram(mermaidSyntax) {
    const container = document.getElementById('mermaidDiagram');
    container.innerHTML = mermaidSyntax;
    
    // Re-render Mermaid diagrams
    mermaid.contentLoaded();
}

/**
 * Update edges table
 */
function updateEdgesTable(edges) {
    if (edges.length === 0) {
        document.getElementById('edgesTable').innerHTML = 
            '<tr><td colspan="4" class="has-text-grey">No edges found</td></tr>';
        return;
    }
    
    let html = '';
    for (const edge of edges) {
        const typeBadge = `<span class="badge edge-type-${edge.type.toLowerCase()}">${edge.type}</span>`;
        const details = edge.details ? `<code>${edge.details}</code>` : '-';
        const via = edge.via ? `<br><small style="color: #999;">via: ${edge.via}</small>` : '';
        
        html += `
            <tr>
                <td><code>${edge.source}</code></td>
                <td><code>${edge.target}</code></td>
                <td>${typeBadge}</td>
                <td>${details}${via}</td>
            </tr>
        `;
    }
    
    document.getElementById('edgesTable').innerHTML = html;
}

/**
 * Clear all data
 */
function clearAll() {
    document.getElementById('ddlInput').value = '';
    document.getElementById('statsContent').innerHTML = '<p class="has-text-grey">No analysis yet</p>';
    document.getElementById('objectsContent').innerHTML = '<p class="has-text-grey">No objects found</p>';
    document.getElementById('cyclesContent').innerHTML = '<p class="has-text-grey">No cycles detected</p>';
    document.getElementById('mermaidDiagram').innerHTML = '<p class="has-text-grey" style="text-align: center; padding: 40px;">Analyze SQL to see diagram</p>';
    document.getElementById('edgesTable').innerHTML = '<tr><td colspan="4" class="has-text-grey">No edges found</td></tr>';
    document.getElementById('topoContent').innerHTML = '<p class="has-text-grey">No topological order</p>';
    document.getElementById('downloadBtn').disabled = true;
    currentAnalysisResult = null;
    hideAllAlerts();
}

/**
 * Switch between tabs
 */
function switchTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('is-active'));
    
    // Show selected tab
    document.getElementById('tab-' + tabName).classList.add('is-active');
    
    // Update active tab styling
    document.querySelectorAll('.tabs li').forEach(li => li.classList.remove('is-active'));
    event.target.parentElement.classList.add('is-active');
}

/**
 * Switch between visualization modes
 */
function switchViz(vizName) {
    // Hide all viz
    document.querySelectorAll('[id^="viz-"]').forEach(v => {
        v.classList.remove('viz-active');
        v.classList.add('viz-inactive');
    });
    
    // Show selected viz
    const vizElement = document.getElementById('viz-' + vizName);
    vizElement.classList.remove('viz-inactive');
    vizElement.classList.add('viz-active');
    
    // Update active tab styling
    document.querySelectorAll('.tabs:last-child li').forEach(li => li.classList.remove('is-active'));
    if (event && event.target) {
        event.target.parentElement.classList.add('is-active');
    }
}

/**
 * Load example SQL
 */
function loadExample(exampleName) {
    const examples = {
        'basic': `CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);

CREATE VIEW active_orders AS
SELECT o.id, o.user_id, COUNT(oi.id) as item_count
FROM orders o
LEFT JOIN order_items oi ON o.id = oi.order_id
GROUP BY o.id, o.user_id;`,

        'cycles': `CREATE TABLE a (id INT PRIMARY KEY);
CREATE TABLE b (id INT PRIMARY KEY, a_id INT REFERENCES a(id));
CREATE VIEW v_a AS SELECT * FROM b WHERE a_id > 0;
CREATE TABLE a_copy AS SELECT * FROM v_a;
ALTER TABLE a ADD FOREIGN KEY (id) REFERENCES a_copy(id);`,

        'complex': `CREATE TABLE customers (
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
$$;`
    };
    
    document.getElementById('ddlInput').value = examples[exampleName] || examples['basic'];
}

/**
 * Download results as JSON
 */
function downloadResults() {
    if (!currentAnalysisResult) {
        showError('No analysis results to download');
        return;
    }
    
    const dataStr = JSON.stringify(currentAnalysisResult.data, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `lineage-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
    
    showSuccess('Results downloaded!');
}

/**
 * Show error message
 */
function showError(message) {
    const alert = document.getElementById('errorAlert');
    document.getElementById('errorText').textContent = message;
    alert.classList.remove('is-hidden');
    
    document.getElementById('successAlert').classList.add('is-hidden');
    
    setTimeout(() => {
        alert.classList.add('is-hidden');
    }, 5000);
}

/**
 * Show success message
 */
function showSuccess(message) {
    const alert = document.getElementById('successAlert');
    document.getElementById('successText').textContent = message;
    alert.classList.remove('is-hidden');
    
    document.getElementById('errorAlert').classList.add('is-hidden');
    
    setTimeout(() => {
        alert.classList.add('is-hidden');
    }, 5000);
}

/**
 * Hide all alerts
 */
function hideAllAlerts() {
    document.getElementById('errorAlert').classList.add('is-hidden');
    document.getElementById('successAlert').classList.add('is-hidden');
}
