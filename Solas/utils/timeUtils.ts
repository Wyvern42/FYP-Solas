export const convertTo24HourFormat = (timeString: string): string | null => {
    if (!timeString) return null;
  
    if (!timeString.includes('AM') && !timeString.includes('PM')) {
      return timeString;
    }
  
    const [time, modifier] = timeString.split(' ');
    let [hours, minutes] = time.split(':');
  
    if (modifier === 'PM' && hours !== '12') {
      hours = (parseInt(hours, 10) + 12).toString();
    } else if (modifier === 'AM' && hours === '12') {
      hours = '00';
    }
  
    return `${hours}:${minutes}`;
  };