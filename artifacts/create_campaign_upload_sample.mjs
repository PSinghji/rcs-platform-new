import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "/Users/pradeepsingh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";

const outputDir = new URL("./", import.meta.url).pathname;
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Campaign Numbers");

sheet.showGridLines = false;
sheet.getRange("A1").values = [["Mobile"]];
sheet.getRange("A2:A4").values = [["9876543210"], ["9123456789"], ["9988776655"]];
sheet.getRange("A1:A4").format.font = { name: "Arial", size: 10, color: "#1F2937" };
sheet.getRange("A1").format = {
  fill: "#245781",
  font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
sheet.getRange("A1:A4").format.borders = { preset: "outside", style: "thin", color: "#D9E2F3" };
sheet.getRange("A2:A4").format.numberFormat = "@";
sheet.getRange("A1:A4").format.columnWidth = 20;
sheet.getRange("A1").format.rowHeight = 24;
sheet.freezePanes.freezeRows(1);

await workbook.recalculate();
console.log((await workbook.inspect({ kind: "region", sheetId: "Campaign Numbers", range: "A1:A4", maxChars: 2000 })).ndjson);
const preview = await workbook.render({ sheetName: "Campaign Numbers", range: "A1:A4", scale: 1.5, format: "png" });
await fs.writeFile(`${outputDir}RCS_Campaign_Bulk_Upload_Template-preview.png`, new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(`${outputDir}RCS_Campaign_Bulk_Upload_Template.xlsx`);
