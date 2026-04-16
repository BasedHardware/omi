import { Card, CardContent } from "../../ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../ui/table";
import type { TableData } from "../types";

export function TableView({ data }: { data: TableData }) {
  if (data.rows.length === 0) return null;
  const [header, ...rows] = data.rows;

  return (
    <Card className="not-prose my-3 gap-0 overflow-hidden border-border/60 py-0">
      {data.title && (
        <div className="flex items-center border-b border-border/40 px-5 py-2.5">
          <p className="text-sm font-semibold text-foreground">{data.title}</p>
        </div>
      )}
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow className="border-border/40 hover:bg-transparent">
              {header.cells.map((c, i) => (
                <TableHead
                  key={i}
                  className="h-9 whitespace-normal px-5 text-xs font-medium text-muted-foreground"
                >
                  {c.content}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, rIdx) => (
              <TableRow
                key={rIdx}
                className="border-border/40 last:border-b-0 hover:bg-accent/30"
              >
                {row.cells.map((c, cIdx) => (
                  <TableCell
                    key={cIdx}
                    className="whitespace-normal px-5 py-2.5 align-top text-sm text-foreground"
                  >
                    {c.content}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
