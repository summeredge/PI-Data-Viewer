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

        public static ReaderOptions Parse(string[] args)
        {
            if (args == null || args.Length == 0)
            {
                throw new ArgumentException("Usage: PIReader.exe --config config.txt --tags tags.txt --start \"...\" --end \"...\"");
            }

            var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            for (var index = 0; index < args.Length; index += 2)
            {
                if (!args[index].StartsWith("--", StringComparison.Ordinal) || index + 1 >= args.Length)
                {
                    throw new ArgumentException("Each option must have a value.");
                }

                var option = args[index].ToLowerInvariant();
                if (option != "--config" && option != "--tags" && option != "--start" && option != "--end")
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
                EndTime = Required(values, "--end")
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
        }

        public static List<string> ReadTags(string path)
        {
            if (!File.Exists(path))
            {
                throw new FileNotFoundException("Tag file not found.", path);
            }

            var tags = new List<string>();
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var rawLine in File.ReadAllLines(path, new UTF8Encoding(false)))
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

        public PiSdkReader(IDictionary<string, string> config)
        {
            _sdk = new PISDKClass();
            _server = _sdk.Servers[config["Server"]];
            _interval = config["Interval"];

            var user = config["User"];
            var password = config["Password"];
            var connection = string.IsNullOrEmpty(user) && string.IsNullOrEmpty(password)
                ? string.Empty
                : string.Format(CultureInfo.InvariantCulture, "UID={0};PWD={1}", user, password);
            _server.Open(connection);
        }

        public List<PiSample> Read(string tag, string startTimeText, string endTimeText)
        {
            PITimeFormat startTime = new PITimeFormatClass();
            startTime.InputString = startTimeText;
            PITimeFormat endTime = new PITimeFormatClass();
            endTime.InputString = endTimeText;

            PIPoint point = _server.PIPoints[tag];
            PIValues values = point.Data.InterpolatedValues2(
                startTime,
                endTime,
                _interval,
                string.Empty,
                FilteredViewConstants.fvRemoveFiltered,
                null);

            var samples = new List<PiSample>();
            foreach (PIValue value in values)
            {
                samples.Add(new PiSample(FormatTimestamp(value), ReaderProtocol.NormalizeValue(value.Value)));
            }

            return samples;
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
            var timestamp = new PITimeFormatClass
            {
                FormatString = "yyyy-MM-dd HH:mm:ss",
                UTCSeconds = value.TimeStamp.UTCSeconds
            };
            return timestamp.OutputString;
        }
    }

    internal static class Program
    {
        private static int Main(string[] args)
        {
            try
            {
                var options = ReaderOptions.Parse(args);
                var config = ReaderProtocol.ReadConfig(options.ConfigPath);
                ReaderProtocol.ValidateConfig(config);
                var tags = ReaderProtocol.ReadTags(options.TagsPath);
                var samplesByTag = new Dictionary<string, List<PiSample>>(StringComparer.OrdinalIgnoreCase);

                using (var reader = new PiSdkReader(config))
                {
                    foreach (var tag in tags)
                    {
                        samplesByTag[tag] = reader.Read(tag, options.StartTime, options.EndTime);
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
    }
}
