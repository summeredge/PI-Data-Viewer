using System;
using System.Globalization;
using System.Text.RegularExpressions;

namespace PIReader
{
    public static class TimeExpressionParser
    {
        private static readonly Regex RelativePattern = new Regex(
            @"^\*(?<sign>[+-])(?<amount>\d+)(?<unit>[smhdw])$",
            RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);

        public static DateTime Parse(string expression, Func<DateTime> currentTimeProvider = null)
        {
            var value = expression == null ? string.Empty : expression.Trim();
            if (value == "*")
            {
                return currentTimeProvider == null ? DateTime.Now : currentTimeProvider();
            }

            var relative = RelativePattern.Match(value);
            if (relative.Success)
            {
                long amount;
                if (!long.TryParse(
                    relative.Groups["amount"].Value,
                    NumberStyles.None,
                    CultureInfo.InvariantCulture,
                    out amount))
                {
                    throw InvalidExpression(value);
                }

                try
                {
                    var currentTime = currentTimeProvider == null ? DateTime.Now : currentTimeProvider();
                    var offset = CreateOffset(amount, relative.Groups["unit"].Value[0]);
                    return relative.Groups["sign"].Value == "-"
                        ? currentTime.Subtract(offset)
                        : currentTime.Add(offset);
                }
                catch (ArgumentOutOfRangeException exception)
                {
                    throw InvalidExpression(value, exception);
                }
                catch (OverflowException exception)
                {
                    throw InvalidExpression(value, exception);
                }
            }

            DateTime fixedTime;
            if (DateTime.TryParse(
                value,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AllowWhiteSpaces,
                out fixedTime))
            {
                return fixedTime;
            }

            throw InvalidExpression(value);
        }

        private static TimeSpan CreateOffset(long amount, char unit)
        {
            switch (char.ToLowerInvariant(unit))
            {
                case 's':
                    return TimeSpan.FromSeconds(amount);
                case 'm':
                    return TimeSpan.FromMinutes(amount);
                case 'h':
                    return TimeSpan.FromHours(amount);
                case 'd':
                    return TimeSpan.FromDays(amount);
                case 'w':
                    return TimeSpan.FromDays(amount * 7.0);
                default:
                    throw new ArgumentException("Unsupported time unit.", "unit");
            }
        }

        private static FormatException InvalidExpression(string expression, Exception inner = null)
        {
            return new FormatException(
                string.Format(
                    CultureInfo.InvariantCulture,
                    "Invalid time expression: {0}\nSupported:\n*\n*-1h\n*-30m\nYYYY-MM-DD HH:MM:SS",
                    expression),
                inner);
        }
    }
}
