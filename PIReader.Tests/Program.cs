using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Web.Script.Serialization;
using PIReader;

namespace PIReader.Tests
{
    internal static class Program
    {
        private static int Main()
        {
            try
            {
                TestReaderOptions();
                TestConfigAndTagsParsing();
                TestResponseSerialization();
                TestNormalizeValue();
                Console.WriteLine("PIReader protocol tests passed.");
                return 0;
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.Message);
                return 1;
            }
        }

        private static void TestReaderOptions()
        {
            foreach (var interval in new[] { "1m", "5m" })
            {
                var options = ReaderOptions.Parse(new[]
                {
                    "--config", "config.txt",
                    "--tags", "tags.txt",
                    "--start", "2026-01-01 00:00:00",
                    "--end", "2026-01-01 12:00:00",
                    "--interval", interval
                });

                Assert(options.ConfigPath == "config.txt", "config argument was not parsed");
                Assert(options.TagsPath == "tags.txt", "tags argument was not parsed");
                Assert(options.StartTime == "2026-01-01 00:00:00", "start argument was not parsed");
                Assert(options.EndTime == "2026-01-01 12:00:00", "end argument was not parsed");
                Assert(options.Interval == interval, "interval argument was not parsed");
            }

            ExpectArgumentException(new[]
            {
                "--config", "config.txt",
                "--tags", "tags.txt",
                "--start", "2026-01-01 00:00:00",
                "--end", "2026-01-01 12:00:00"
            }, "--interval");
            ExpectArgumentException(new[] { "--unknown", "value" }, "Unknown option");
        }

        private static void TestConfigAndTagsParsing()
        {
            var root = Path.Combine(Path.GetTempPath(), "pi-reader-tests-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            try
            {
                var configPath = Path.Combine(root, "config.txt");
                File.WriteAllText(
                    configPath,
                    "\uFEFF# shared PIExport format\nServer=PI-SERVER\nUser=PI-USER\nPassword=PI-PASSWORD\nInterval=1m\nBlockDays=3\n",
                    new UTF8Encoding(false));
                var config = ReaderProtocol.ReadConfig(configPath);
                ReaderProtocol.ValidateConfig(config);
                Assert(config["Server"] == "PI-SERVER", "config value was not parsed");

                var tagsPath = Path.Combine(root, "tags.txt");
                File.WriteAllText(tagsPath, "\uFEFFTAG_A\n# ignored\nTAG_A\nTAG_B\n", new UTF8Encoding(false));
                var tags = ReaderProtocol.ReadTags(tagsPath);
                Assert(tags.Count == 2 && tags[0] == "TAG_A" && tags[1] == "TAG_B", "tags were not ordered/deduplicated");
            }
            finally
            {
                Directory.Delete(root, true);
            }
        }

        private static void TestResponseSerialization()
        {
            var tags = new List<string> { "TAG_A", "TAG_B" };
            var samples = new Dictionary<string, List<PiSample>>(StringComparer.OrdinalIgnoreCase);
            samples["TAG_A"] = new List<PiSample>
            {
                new PiSample("2026-01-01 00:00:00", 85.2),
                new PiSample("2026-01-01 00:01:00", null)
            };
            samples["TAG_B"] = new List<PiSample>
            {
                new PiSample("2026-01-01 00:00:00", 1.25),
                new PiSample("2026-01-01 00:01:00", 1.26)
            };

            var response = ReaderProtocol.BuildResponse(tags, samples);
            var payload = Parse(ReaderProtocol.Serialize(response));
            var columns = AsList(payload["columns"]);
            var data = AsList(payload["data"]);
            Assert(columns.Count == 3 && (string)columns[0] == "Timestamp" && (string)columns[2] == "TAG_B", "columns are invalid");
            Assert(data.Count == 2, "multi-tag rows are missing");
            var firstRow = AsList(data[0]);
            var secondRow = AsList(data[1]);
            Assert((string)firstRow[0] == "2026-01-01 00:00:00", "timestamp is invalid");
            Assert(Convert.ToDouble(firstRow[1]) == 85.2 && Convert.ToDouble(firstRow[2]) == 1.25, "multi-tag values are invalid");
            Assert(secondRow[1] == null && Convert.ToDouble(secondRow[2]) == 1.26, "null values are invalid");

            var empty = ReaderProtocol.BuildResponse(
                tags,
                new Dictionary<string, List<PiSample>>(StringComparer.OrdinalIgnoreCase));
            var emptyPayload = Parse(ReaderProtocol.Serialize(empty));
            Assert(AsList(emptyPayload["columns"]).Count == 3, "empty response lost columns");
            Assert(AsList(emptyPayload["data"]).Count == 0, "empty response contains rows");
        }

        private static void TestNormalizeValue()
        {
            Assert(ReaderProtocol.NormalizeValue(null) == null, "null value was not normalized");
            Assert(ReaderProtocol.NormalizeValue(DBNull.Value) == null, "DBNull was not normalized");
            Assert(ReaderProtocol.NormalizeValue(double.NaN) == null, "NaN was not normalized");
            Assert(ReaderProtocol.NormalizeValue(double.PositiveInfinity) == null, "infinity was not normalized");
            Assert(Convert.ToDouble(ReaderProtocol.NormalizeValue(12)) == 12.0, "integer was not normalized");
            Assert(Convert.ToDouble(ReaderProtocol.NormalizeValue(12.5m)) == 12.5, "decimal was not normalized");
            Assert((string)ReaderProtocol.NormalizeValue("text") == "text", "string was changed");
            Assert((bool)ReaderProtocol.NormalizeValue(true), "boolean was changed");
        }

        private static void ExpectArgumentException(string[] args, string expectedText)
        {
            try
            {
                ReaderOptions.Parse(args);
            }
            catch (ArgumentException exception)
            {
                Assert(exception.Message.IndexOf(expectedText, StringComparison.OrdinalIgnoreCase) >= 0, "unexpected argument error");
                return;
            }

            throw new InvalidOperationException("FAIL: invalid arguments were accepted");
        }

        private static Dictionary<string, object> Parse(string json)
        {
            return new JavaScriptSerializer().DeserializeObject(json) as Dictionary<string, object>;
        }

        private static IList AsList(object value)
        {
            var list = value as IList;
            Assert(list != null, "JSON array is invalid");
            return list;
        }

        private static void Assert(bool condition, string message)
        {
            if (!condition)
            {
                throw new InvalidOperationException("FAIL: " + message);
            }
        }
    }
}
