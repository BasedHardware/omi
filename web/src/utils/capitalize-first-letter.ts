export default function capitalizeFirstLetter(str: string) {
  if (str === 'ceo') {
    return str.toUpperCase();
  }
  let formattedStr = str.replace(/_/g, ' ');
  formattedStr = formattedStr.replace(/ai/g, 'AI');
  return formattedStr.charAt(0).toUpperCase() + formattedStr.slice(1);
}
