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
                TestArgumentParsing();
                TestConfigAndTagsParsing();
                TestMultiTagJson();
                TestEmptyJson();
                Console.WriteLine("PIReader protocol tests passed.");
                return 0;
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.Message);
                return 1;
            }
        }

        private static void TestArgumentParsing()
        {
            var options = ReaderOptions.Parse(new[]
            {
                "--config", "config.txt",
                "--tags", "tags.txt",
                "--start", "2026-01-01 00:00:00",
                "--end", "2026-01-01 12:00:00"
            });

            Assert(options.ConfigPath == "config.txt", "config argument was not parsed");
            Assert(options.TagsPath == "tags.txt", "tags argument was not parsed");
            Assert(options.StartTime == "2026-01-01 00:00:00", "start argument was not parsed");
            Assert(options.EndTime == "2026-01-01 12:00:00", "end argument was not parsed");
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

        private static void TestMultiTagJson()
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

            var payload = Parse(ReaderProtocol.Serialize(ReaderProtocol.BuildResponse(tags, samples)));
            var columns = AsList(payload["columns"]);
            var data = AsList(payload["data"]);
            Assert(columns.Count == 3 && (string)columns[0] == "Timestamp" && (string)columns[2] == "TAG_B", "columns are invalid");
            Assert(data.Count == 2, "multi-tag rows are missing");
            var firstRow = AsList(data[0]);
            var secondRow = AsList(data[1]);
            Assert((string)firstRow[0] == "2026-01-01 00:00:00", "timestamp is invalid");
            Assert(Convert.ToDouble(firstRow[1]) == 85.2 && Convert.ToDouble(firstRow[2]) == 1.25, "multi-tag values are invalid");
            Assert(secondRow[1] == null && Convert.ToDouble(secondRow[2]) == 1.26, "null values are invalid");
        }

        private static void TestEmptyJson()
        {
            var tags = new List<string> { "TAG_A", "TAG_B" };
            var samples = new Dictionary<string, List<PiSample>>(StringComparer.OrdinalIgnoreCase);
            var payload = Parse(ReaderProtocol.Serialize(ReaderProtocol.BuildResponse(tags, samples)));
            Assert(AsList(payload["columns"]).Count == 3, "empty response lost columns");
            Assert(AsList(payload["data"]).Count == 0, "empty response contains rows");
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
