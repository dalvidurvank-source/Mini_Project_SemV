import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import {
  ArrowRight,
  BarChart3,
  MapPinned,
  PackageCheck,
  ShieldCheck,
  Sprout,
  TrendingUp,
  Truck,
  Wheat,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import './App.css'

const marketTrend = [
  { month: 'Jan', price: 640 },
  { month: 'Feb', price: 685 },
  { month: 'Mar', price: 670 },
  { month: 'Apr', price: 705 },
  { month: 'May', price: 735 },
  { month: 'Jun', price: 760 },
  { month: 'Jul', price: 748 },
  { month: 'Aug', price: 772 },
]

const qualityMix = [
  { name: 'Grade A', value: 52, color: '#2e7d52' },
  { name: 'Grade B', value: 34, color: '#8bc34a' },
  { name: 'Grade C', value: 14, color: '#d0d6a5' },
]

const priceBreakdown = [
  { name: 'VAR base', value: 743.05 },
  { name: 'DSR uplift', value: 52.4 },
  { name: 'Quality premium', value: 36.75 },
  { name: 'Transport deduction', value: -42.5 },
  { name: 'Platform overhead', value: -14.3 },
]

const routeSummary = [
  { name: 'Hub A', cost: 180 },
  { name: 'Hub B', cost: 210 },
  { name: 'Hub C', cost: 245 },
]

const pricingResult = {
  basePrice: 743.05,
  dsr: 0.9,
  dsrMultiplier: 1.01,
  qualityMultiplier: 1.05,
  locationMultiplier: 1.0,
  transportCost: 160,
  fairPrice: 761.2,
  minPrice: 736.2,
  maxPrice: 786.2,
}

const dashboardCards = [
  { icon: TrendingUp, label: 'Forecasted price', value: '₹743 /q', detail: '+6.4% vs last cycle' },
  { icon: PackageCheck, label: 'Inventory health', value: '92%', detail: 'Good volume quality mix' },
  { icon: Truck, label: 'Transportation', value: '₹160/q', detail: 'Nearest mandi route' },
  { icon: ShieldCheck, label: 'Fairness index', value: '89/100', detail: 'Within approved band' },
]

const navigation = [
  { to: '/', label: 'Overview' },
  { to: '/market', label: 'Market' },
  { to: '/pricing', label: 'Pricing' },
  { to: '/farmer', label: 'Farmer' },
  { to: '/insights', label: 'Insights' },
]

function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <header className="topbar">
          <div className="brand-wrap">
            <div className="brand-mark">
              <Wheat size={20} />
            </div>
            <div>
              <div className="brand-name">AgroLink</div>
              <div className="brand-subtitle">Fair price exchange</div>
            </div>
          </div>

          <nav className="main-nav" aria-label="Main navigation">
            {navigation.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `nav-link ${isActive ? 'active' : ''}`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <button type="button" className="primary-button">
            Connect farmer
            <ArrowRight size={16} />
          </button>
        </header>

        <main className="page-content">
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/market" element={<MarketPage />} />
            <Route path="/pricing" element={<PricingPage />} />
            <Route path="/farmer" element={<FarmerPage />} />
            <Route path="/insights" element={<InsightsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

function OverviewPage() {
  return (
    <>
      <section className="hero-panel">
        <div className="hero-copy">
          <span className="eyebrow">Transparent agricultural commerce</span>
          <h1>Explainable pricing for a fairer farm-to-market exchange.</h1>
          <p>
            AgroLink blends mandi market intelligence, demand-supply signals and
            transport logic to recommend a defensible fair price without hidden
            middlemen margins.
          </p>
          <div className="hero-actions">
            <button type="button" className="primary-button">
              View pricing model
            </button>
            <button type="button" className="secondary-button">
              Explore market
            </button>
          </div>
          <ul className="hero-metrics">
            <li>
              <strong>₹612L</strong>
              <span>trade volume tracked</span>
            </li>
            <li>
              <strong>41 hubs</strong>
              <span>connected to price engine</span>
            </li>
            <li>
              <strong>89% trust</strong>
              <span>farmer confidence score</span>
            </li>
          </ul>
        </div>

        <div className="hero-visual">
          <div className="mini-panel metric-panel large">
            <div className="panel-label-row">
              <span className="panel-kicker">Live forecast</span>
              <span className="status-pill">Stable</span>
            </div>
            <div className="big-number">₹761.2</div>
            <div className="trend-line">
              <span>fair price</span>
              <strong>+8.1% MoM</strong>
            </div>
          </div>

          <div className="mini-panel chart-panel">
            <div className="panel-label-row">
              <span className="panel-kicker">Base market</span>
              <MapPinned size={14} />
            </div>
            <div className="sparkline">
              <span className="bar h-35" />
              <span className="bar h-45" />
              <span className="bar h-60" />
              <span className="bar h-50" />
              <span className="bar h-75" />
              <span className="bar h-85" />
              <span className="bar h-95" />
              <span className="bar h-80" />
            </div>
          </div>
        </div>
      </section>

      <section className="card-grid four-up">
        {dashboardCards.map(({ icon: Icon, label, value, detail }) => (
          <article key={label} className="stat-card">
            <div className="stat-icon-wrap">
              <Icon size={18} />
            </div>
            <div>
              <p>{label}</p>
              <h3>{value}</h3>
              <span>{detail}</span>
            </div>
          </article>
        ))}
      </section>

      <section className="content-grid two-col">
        <article className="panel">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">Market trend</span>
              <h2>Tomato price movement</h2>
            </div>
            <div className="pill neutral">Last 8 months</div>
          </div>

          <div className="chart-wrap medium">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={marketTrend}>
                <defs>
                  <linearGradient id="priceFill" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#2e7d52" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#2e7d52" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(33, 52, 39, 0.12)" />
                <XAxis dataKey="month" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} />
                <Tooltip />
                <Area type="monotone" dataKey="price" stroke="#2e7d52" fill="url(#priceFill)" strokeWidth={3} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="panel">
          <div className="panel-header">
            <div>
              <span className="panel-kicker">Quality mix</span>
              <h2>Grade distribution</h2>
            </div>
            <div className="pill neutral">Batch snapshot</div>
          </div>

          <div className="chart-wrap small">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={qualityMix} dataKey="value" innerRadius={48} outerRadius={68} paddingAngle={3}>
                  {qualityMix.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="legend-list">
            {qualityMix.map((item) => (
              <div key={item.name} className="legend-row">
                <span className="dot" style={{ backgroundColor: item.color }} />
                <span>{item.name}</span>
                <strong>{item.value}%</strong>
              </div>
            ))}
          </div>
        </article>
      </section>
    </>
  )
}

function MarketPage() {
  return (
    <section className="single-panel">
      <div className="panel-header">
        <div>
          <span className="panel-kicker">Market intelligence</span>
          <h2>Regional mandi overview</h2>
        </div>
        <div className="pill neutral">Updated 12 min ago</div>
      </div>

      <div className="content-grid two-col compact">
        <article className="panel inset-panel">
          <div className="mini-title">Nearest routes</div>
          <div className="route-list">
            {routeSummary.map((route) => (
              <div key={route.name} className="route-item">
                <div>
                  <strong>{route.name}</strong>
                  <span>Throughput efficient</span>
                </div>
                <div className="route-cost">₹{route.cost}</div>
              </div>
            ))}
          </div>
        </article>

        <article className="panel inset-panel">
          <div className="mini-title">Supply-demand balance</div>
          <div className="chart-wrap medium small-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={routeSummary}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(33, 52, 39, 0.10)" />
                <XAxis dataKey="name" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} />
                <Tooltip />
                <Bar dataKey="cost" fill="#2e7d52" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </article>
      </div>
    </section>
  )
}

function PricingPage() {
  return (
    <section className="single-panel">
      <div className="panel-header">
        <div>
          <span className="panel-kicker">Fair-price engine</span>
          <h2>Explainable price recommendation</h2>
        </div>
        <div className="pill positive">Approved band</div>
      </div>

      <div className="price-stage">
        <div className="price-highlight">
          <span>Recommended fair price</span>
          <strong>₹{pricingResult.fairPrice.toFixed(2)}</strong>
          <div className="range-row">
            <span>Min ₹{pricingResult.minPrice.toFixed(2)}</span>
            <span>Max ₹{pricingResult.maxPrice.toFixed(2)}</span>
          </div>
        </div>

        <div className="price-breakdown">
          {priceBreakdown.map((item) => (
            <div key={item.name} className="breakdown-row">
              <span>{item.name}</span>
              <strong>{item.value > 0 ? '+' : ''}₹{item.value.toFixed(2)}</strong>
            </div>
          ))}
        </div>
      </div>

      <div className="info-grid three-up">
        <article className="info-card">
          <div className="info-card-label">VAR base price</div>
          <div className="info-card-value">₹{pricingResult.basePrice.toFixed(2)}</div>
        </article>
        <article className="info-card">
          <div className="info-card-label">DSR</div>
          <div className="info-card-value">{pricingResult.dsr.toFixed(2)}</div>
        </article>
        <article className="info-card">
          <div className="info-card-label">DSR multiplier</div>
          <div className="info-card-value">{pricingResult.dsrMultiplier.toFixed(2)}</div>
        </article>
        <article className="info-card">
          <div className="info-card-label">Quality multiplier</div>
          <div className="info-card-value">{pricingResult.qualityMultiplier.toFixed(2)}</div>
        </article>
        <article className="info-card">
          <div className="info-card-label">Location multiplier</div>
          <div className="info-card-value">{pricingResult.locationMultiplier.toFixed(2)}</div>
        </article>
        <article className="info-card">
          <div className="info-card-label">Transport cost</div>
          <div className="info-card-value">₹{pricingResult.transportCost}</div>
        </article>
      </div>
    </section>
  )
}

function FarmerPage() {
  return (
    <section className="single-panel">
      <div className="panel-header">
        <div>
          <span className="panel-kicker">Farmer workflow</span>
          <h2>Listing and fulfillment status</h2>
        </div>
        <div className="pill positive">Ready for market</div>
      </div>

      <div className="farmer-grid">
        <article className="panel inset-panel">
          <div className="mini-title">Listing summary</div>
          <ul className="detail-list">
            <li>
              <span>Crop</span>
              <strong>Tomato</strong>
            </li>
            <li>
              <span>Quality grade</span>
              <strong>A</strong>
            </li>
            <li>
              <span>Location</span>
              <strong>Hapur mandi</strong>
            </li>
            <li>
              <span>Net expected revenue</span>
              <strong>₹1,42,300</strong>
            </li>
          </ul>
        </article>

        <article className="panel inset-panel">
          <div className="mini-title">Fulfillment health</div>
          <div className="progress-stack">
            <div>
              <div className="progress-row">
                <span>Inventory matched</span>
                <strong>92%</strong>
              </div>
              <div className="progress-bar"><span style={{ width: '92%' }} /></div>
            </div>
            <div>
              <div className="progress-row">
                <span>Buyer demand</span>
                <strong>84%</strong>
              </div>
              <div className="progress-bar"><span style={{ width: '84%' }} /></div>
            </div>
            <div>
              <div className="progress-row">
                <span>Logistics match</span>
                <strong>76%</strong>
              </div>
              <div className="progress-bar"><span style={{ width: '76%' }} /></div>
            </div>
          </div>
        </article>
      </div>
    </section>
  )
}

function InsightsPage() {
  return (
    <section className="single-panel">
      <div className="panel-header">
        <div>
          <span className="panel-kicker">Operational insights</span>
          <h2>Demand-supply intelligence</h2>
        </div>
        <div className="pill neutral">Updated daily</div>
      </div>

      <div className="info-grid three-up">
        <article className="info-card insight-card">
          <div className="info-card-label"><Sprout size={16} /> Supply signal</div>
          <div className="info-card-value">+12.4%</div>
        </article>
        <article className="info-card insight-card">
          <div className="info-card-label"><BarChart3 size={16} /> Demand index</div>
          <div className="info-card-value">8.1/10</div>
        </article>
        <article className="info-card insight-card">
          <div className="info-card-label"><Truck size={16} /> Route efficiency</div>
          <div className="info-card-value">91%</div>
        </article>
      </div>
    </section>
  )
}

export default App
