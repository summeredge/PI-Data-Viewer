using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using System.Web.Script.Serialization;
using PISDK;
using PITimeServer;

namespace PIReader
{
    public sealed class ReaderOptions
    {
        public string ConfigPath { get; private set; }
        public string TagsPath { get; private set; }
        public string StartTime { get; private set; }
        public string EndTime { get; private set; }
        public string Interval { get; private set; }

        public static ReaderOptions Parse(string[] args)
        {
            if (args == null || args.Length == 0)
            {
                throw new ArgumentException("Usage: PIReader.exe --config config.txt --tags tags.txt (or --tags - for stdin) --start \"...\" --end \"...\" --interval 1m");
            }

            var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            for (var index = 0; index < args.Length; index += 2)
            {
                if (!args[index].StartsWith("--", StringComparison.Ordinal) || index + 1 >= args.Length)
                {
                    throw new ArgumentException("Each option must have a value.");
                }

                var option = args[index].ToLowerInvariant();
                if (option != "--config" && option != "--tags" && option != "--start" && option != "--end" && option != "--interval")
                {
                    throw new ArgumentException("Unknown option: " + args[index]);
                }

                values[option] = args[index + 1];
            }

            return new ReaderOptions
            {
                ConfigPath = Required(values, "--config"),
                TagsPath = Required(values, "--tags"),
                StartTime = Required(values, "--start"),
                EndTime = Required(values, "--end"),
                Interval = Required(values, "--interval")
            };
        }

        private static string Required(IDictionary<string, string> values, string name)
        {
            string value;
            if (!values.TryGetValue(name, out value) || string.IsNullOrWhiteSpace(value))
            {
                throw new ArgumentException("Missing option: " + name);
            }

            return value;
        }
    }

    public sealed class SearchOptions
    {
        public const int DefaultMaxResults = 100;

        public string ConfigPath { get; private set; }
        public string Mask { get; private set; }

        public static bool IsSearch(string[] args)
        {
            if (args == null)
            {
                return false;
            }

            foreach (var arg in args)
            {
                if (string.Equals(arg, "--search", StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }

            return false;
        }

        public static SearchOptions Parse(string[] args)
        {
            if (args == null || args.Length == 0)
            {
                throw new ArgumentException("Usage: PIReader.exe [--config config.txt] --search --mask \"FIC*\"");
            }

            var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            var searchRequested = false;
            for (var index = 0; index < args.Length;)
            {
                var option = args[index].ToLowerInvariant();
                if (option == "--search")
                {
                    searchRequested = true;
                    index++;
                    continue;
                }

                if (option != "--config" && option != "--mask")
                {
                    throw new ArgumentException("Unknown option: " + args[index]);
                }

                if (index + 1 >= args.Length)
                {
                    throw new ArgumentException("Each option must have a value.");
                }

                values[option] = args[index + 1];
                index += 2;
            }

            if (!searchRequested)
            {
                throw new ArgumentException("Search mode requires --search.");
            }

            string rawMask;
            if (!values.TryGetValue("--mask", out rawMask))
            {
                throw new ArgumentException("Missing option: --mask");
            }
            if (string.IsNullOrWhiteSpace(rawMask))
            {
                throw new ArgumentException("Search mask must not be empty.");
            }

            var mask = rawMask.Trim();
            if (mask == "*")
            {
                throw new ArgumentException("Search mask '*' is not allowed; please narrow the condition.");
            }

            return new SearchOptions
            {
                ConfigPath = values.ContainsKey("--config") ? Required(values, "--config") : "config.txt",
                Mask = mask
            };
        }

        private static string Required(IDictionary<string, string> values, string name)
        {
            string value;
            if (!values.TryGetValue(name, out value) || string.IsNullOrWhiteSpace(value))
            {
                throw new ArgumentException("Missing option: " + name);
            }

            return value;
        }
    }

    public sealed class PiSample
    {
        public PiSample(string timestamp, object value)
        {
            Timestamp = timestamp;
            Value = value;
        }

        public string Timestamp { get; private set; }
        public object Value { get; private set; }
    }

    public static class ReaderProtocol
    {
        public static Dictionary<string, string> ReadConfig(string path)
        {
            if (!File.Exists(path))
            {
                throw new FileNotFoundException("PI config file not found.", path);
            }

            var config = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (var rawLine in File.ReadAllLines(path, new UTF8Encoding(false)))
            {
                var line = rawLine.Trim().TrimStart('\uFEFF');
                if (line.Length == 0 || line.StartsWith("#", StringComparison.Ordinal))
                {
                    continue;
                }

                var separator = line.IndexOf('=');
                if (separator <= 0)
                {
                    continue;
                }

                var key = line.Substring(0, separator).Trim();
                if (key.Length > 0)
                {
                    config[key] = line.Substring(separator + 1).Trim();
                }
            }

            return config;
        }

        public static void ValidateConfig(IDictionary<string, string> config)
        {
            foreach (var required in new[] { "Server", "User", "Password", "Interval", "BlockDays" })
            {
                string value;
                if (!config.TryGetValue(required, out value))
                {
                    throw new FormatException("PI config is missing: " + required);
                }
            }

            if (string.IsNullOrWhiteSpace(config["Server"]) || string.IsNullOrWhiteSpace(config["Interval"]))
            {
                throw new FormatException("PI config requires non-empty Server and Interval.");
            }

            GetBlockDays(config);
        }

        public static int GetBlockDays(IDictionary<string, string> config)
        {
            string value;
            int blockDays;
            if (!config.TryGetValue("BlockDays", out value) ||
                !int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out blockDays) ||
                blockDays <= 0)
            {
                throw new FormatException("PI config BlockDays must be a positive integer.");
            }

            return blockDays;
        }

        public static List<string> ReadTags(string path)
        {
            if (path == "-")
            {
                return ParseTags(Console.In.ReadToEnd().Split(new[] { "\r\n", "\n", "\r" }, StringSplitOptions.None));
            }

            if (!File.Exists(path))
            {
                throw new FileNotFoundException("Tag file not found.", path);
            }

            return ParseTags(File.ReadAllLines(path, new UTF8Encoding(false)));
        }

        public static string BuildSearchQuery(string mask)
        {
            if (string.IsNullOrWhiteSpace(mask))
            {
                throw new ArgumentException("Search mask must not be empty.");
            }

            var normalizedMask = mask.Trim();
            if (normalizedMask == "*")
            {
                throw new ArgumentException("Search mask '*' is not allowed; please narrow the condition.");
            }

            return "tag='" + normalizedMask.Replace("'", "''") + "'";
        }

        public static Dictionary<string, object> SearchPoints(
            string mask,
            int maxResults,
            Func<string, IEnumerable<string>> getPointNames)
        {
            if (getPointNames == null)
            {
                throw new ArgumentNullException("getPointNames");
            }

            return BuildSearchResponse(getPointNames(BuildSearchQuery(mask)), maxResults);
        }

        public static Dictionary<string, object> BuildSearchResponse(
            IEnumerable<string> pointNames,
            int maxResults)
        {
            if (pointNames == null)
            {
                throw new ArgumentNullException("pointNames");
            }
            if (maxResults <= 0)
            {
                throw new ArgumentOutOfRangeException("maxResults");
            }

            var tags = new List<string>();
            var truncated = false;
            foreach (var pointName in pointNames)
            {
                if (tags.Count >= maxResults)
                {
                    truncated = true;
                    break;
                }

                tags.Add(pointName);
            }

            var response = new Dictionary<string, object>
            {
                { "count", tags.Count },
                { "tags", tags }
            };
            if (truncated)
            {
                response["truncated"] = true;
                response["message"] = "搜索结果超过限制，请缩小条件";
            }

            return response;
        }

        private static List<string> ParseTags(IEnumerable<string> lines)
        {
            var tags = new List<string>();
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var rawLine in lines)
            {
                var tag = rawLine.Trim().TrimStart('\uFEFF');
                if (tag.Length == 0 || tag.StartsWith("#", StringComparison.Ordinal) || !seen.Add(tag))
                {
                    continue;
                }

                tags.Add(tag);
            }

            if (tags.Count == 0)
            {
                throw new FormatException("Tag file must contain at least one tag.");
            }

            return tags;
        }

        public static Dictionary<string, object> BuildResponse(
            IList<string> tags,
            IDictionary<string, List<PiSample>> samplesByTag)
        {
            var rowsByTimestamp = new SortedDictionary<string, Dictionary<string, object>>(StringComparer.Ordinal);
            foreach (var tag in tags)
            {
                List<PiSample> samples;
                if (!samplesByTag.TryGetValue(tag, out samples))
                {
                    continue;
                }

                foreach (var sample in samples)
                {
                    if (sample == null || string.IsNullOrWhiteSpace(sample.Timestamp))
                    {
                        continue;
                    }

                    Dictionary<string, object> row;
                    if (!rowsByTimestamp.TryGetValue(sample.Timestamp, out row))
                    {
                        row = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);
                        rowsByTimestamp[sample.Timestamp] = row;
                    }

                    row[tag] = sample.Value;
                }
            }

            var data = new List<List<object>>();
            foreach (var rowEntry in rowsByTimestamp)
            {
                var row = new List<object> { rowEntry.Key };
                foreach (var tag in tags)
                {
                    object value;
                    row.Add(rowEntry.Value.TryGetValue(tag, out value) ? value : null);
                }

                data.Add(row);
            }

            var columns = new List<string>(tags.Count + 1) { "Timestamp" };
            columns.AddRange(tags);

            return new Dictionary<string, object>
            {
                { "columns", columns },
                { "data", data }
            };
        }

        public static string Serialize(Dictionary<string, object> response)
        {
            var serializer = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
            return serializer.Serialize(response);
        }

        public static object NormalizeValue(object value)
        {
            if (value == null || value == DBNull.Value)
            {
                return null;
            }

            if (value is double)
            {
                var number = (double)value;
                return double.IsNaN(number) || double.IsInfinity(number) ? null : (object)number;
            }

            if (value is float)
            {
                var number = (float)value;
                return float.IsNaN(number) || float.IsInfinity(number) ? null : (object)number;
            }

            if (value is decimal || value is byte || value is sbyte || value is short || value is ushort ||
                value is int || value is uint || value is long || value is ulong)
            {
                return Convert.ToDouble(value, CultureInfo.InvariantCulture);
            }

            return value is string || value is bool ? value : value.ToString();
        }
    }

    internal sealed class PiSdkReader : IDisposable
    {
        private readonly PISDKClass _sdk;
        private readonly Server _server;
        private readonly string _interval;
        private readonly int _blockDays;

        public PiSdkReader(IDictionary<string, string> config, string interval, int blockDays)
        {
            _sdk = new PISDKClass();
            _server = _sdk.Servers[config["Server"]];
            _interval = interval;
            _blockDays = blockDays;

            var user = config["User"];
            var password = config["Password"];
            var connection = string.IsNullOrEmpty(user) && string.IsNullOrEmpty(password)
                ? string.Empty
                : string.Format(CultureInfo.InvariantCulture, "UID={0};PWD={1}", user, password);
            _server.Open(connection);
        }

        public Dictionary<string, object> Search(string mask, int maxResults)
        {
            return ReaderProtocol.SearchPoints(
                mask,
                maxResults,
                query =>
                {
                    PointList points = _server.GetPoints(query);
                    return PointNames(points);
                });
        }

        private static IEnumerable<string> PointNames(PointList points)
        {
            foreach (PIPoint point in points)
            {
                yield return point.Name;
            }
        }

        public void ResolveTimeRange(
            string startTimeText,
            string endTimeText,
            out DateTime startTime,
            out DateTime endTime)
        {
            var currentTime = GetCurrentServerTime();
            startTime = TimeExpressionParser.Parse(startTimeText, () => currentTime);
            endTime = TimeExpressionParser.Parse(endTimeText, () => currentTime);
            if (endTime <= startTime)
            {
                throw new ArgumentException("End time must be later than start time.");
            }
        }

        public List<PiSample> Read(string tag, DateTime startTime, DateTime endTime)
        {
            if (endTime <= startTime)
            {
                throw new ArgumentException("End time must be later than start time.");
            }

            PIPoint point = _server.PIPoints[tag];
            IPIData2 data = (IPIData2)point.Data;
            var samples = new List<PiSample>();
            var blockStart = startTime;
            while (blockStart < endTime)
            {
                DateTime blockEnd;
                try
                {
                    blockEnd = blockStart.AddDays(_blockDays);
                }
                catch (ArgumentOutOfRangeException)
                {
                    blockEnd = endTime;
                }

                if (blockEnd > endTime)
                {
                    blockEnd = endTime;
                }

                PIValues values = data.InterpolatedValues2(
                    blockStart,
                    blockEnd,
                    _interval);
                foreach (PIValue value in values)
                {
                    var timestamp = FormatTimestamp(value);
                    if (samples.Count == 0 || samples[samples.Count - 1].Timestamp != timestamp)
                    {
                        samples.Add(new PiSample(timestamp, ReaderProtocol.NormalizeValue(value.Value)));
                    }
                }

                blockStart = blockEnd;
            }

            return samples;
        }

        private DateTime GetCurrentServerTime()
        {
            try
            {
                PITimeFormat currentTime = new PITimeFormatClass();
                currentTime.InputString = "*";
                return currentTime.LocalDate;
            }
            catch (Exception)
            {
                return DateTime.Now;
            }
        }

        public void Dispose()
        {
            if (_server != null && _server.Connected)
            {
                _server.Close();
            }
        }

        private static string FormatTimestamp(PIValue value)
        {
            return value.TimeStamp.LocalDate.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture);
        }
    }

    internal static class Program
    {
        private static int Main(string[] args)
        {
            Console.InputEncoding = new UTF8Encoding(false);
            Console.OutputEncoding = new UTF8Encoding(false);
            Console.SetError(new StreamWriter(Console.OpenStandardError(), Console.OutputEncoding) { AutoFlush = true });

            try
            {
                if (SearchOptions.IsSearch(args))
                {
                    return RunSearch(SearchOptions.Parse(args));
                }

                var options = ReaderOptions.Parse(args);
                var config = ReaderProtocol.ReadConfig(options.ConfigPath);
                ReaderProtocol.ValidateConfig(config);
                var tags = ReaderProtocol.ReadTags(options.TagsPath);
                var blockDays = ReaderProtocol.GetBlockDays(config);
                var samplesByTag = new Dictionary<string, List<PiSample>>(StringComparer.OrdinalIgnoreCase);

                using (var reader = new PiSdkReader(config, options.Interval, blockDays))
                {
                    DateTime startTime;
                    DateTime endTime;
                    reader.ResolveTimeRange(options.StartTime, options.EndTime, out startTime, out endTime);
                    foreach (var tag in tags)
                    {
                        samplesByTag[tag] = reader.Read(tag, startTime, endTime);
                    }
                }

                var response = ReaderProtocol.BuildResponse(tags, samplesByTag);
                Console.Out.Write(ReaderProtocol.Serialize(response));
                return 0;
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine("PIReader: " + exception.Message);
                return 1;
            }
        }

        private static int RunSearch(SearchOptions options)
        {
            var config = ReaderProtocol.ReadConfig(options.ConfigPath);
            ReaderProtocol.ValidateConfig(config);
            Dictionary<string, object> response;
            using (var reader = new PiSdkReader(
                config,
                config["Interval"],
                ReaderProtocol.GetBlockDays(config)))
            {
                response = reader.Search(options.Mask, SearchOptions.DefaultMaxResults);
            }

            Console.Out.Write(ReaderProtocol.Serialize(response));
            return 0;
        }
    }
}
