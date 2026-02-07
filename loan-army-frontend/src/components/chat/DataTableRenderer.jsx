export function DataTableRenderer({ data }) {
    if (!data) return null

    const { title, columns, data: rows } = data
    if (!rows || !rows.length) return null

    const cols = columns || Object.keys(rows[0] || {})

    return (
        <div className="mt-2 overflow-x-auto">
            {title && <p className="text-xs font-medium text-gray-600 mb-1">{title}</p>}
            <table className="text-xs border-collapse w-full">
                <thead>
                    <tr>
                        {cols.map(col => (
                            <th key={col} className="border border-gray-300 px-2 py-1 bg-gray-50 text-left font-medium">
                                {col}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.slice(0, 50).map((row, i) => (
                        <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                            {cols.map(col => (
                                <td key={col} className="border border-gray-300 px-2 py-1">
                                    {row[col] != null ? String(row[col]) : ''}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
            {rows.length > 50 && (
                <p className="text-xs text-gray-400 mt-1">Showing first 50 of {rows.length} rows</p>
            )}
        </div>
    )
}
